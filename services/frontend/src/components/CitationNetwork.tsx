import { useEffect, useRef, useState } from 'react'
import { useAuthStore } from '../stores/authStore'
import toast from 'react-hot-toast'
import * as d3 from 'd3'
import { MagnifyingGlassIcon, XMarkIcon, ArrowsPointingOutIcon, ArrowsPointingInIcon, QuestionMarkCircleIcon } from '@heroicons/react/24/outline'

interface Node extends d3.SimulationNodeDatum {
  id: string
  title: string
  authors: string[]
  year: number | null
  citation_count: number
  in_degree: number
  journal?: string
  doi?: string
  type: string
}

interface Edge {
  id: string
  source: string | Node
  target: string | Node
  type: string
}

interface GraphData {
  nodes: Node[]
  edges: Edge[]
  metrics: {
    total_papers: number
    total_citations: number
    avg_citations_per_paper: number
    total_internal_citations: number
    most_influential_papers: Array<{
      id: string
      title: string
      in_degree: number
    }>
  }
}

interface CitationNetworkProps {
  projectId: string
}

export default function CitationNetwork({ projectId }: CitationNetworkProps) {
  const { session } = useAuthStore()
  const svgRef = useRef<SVGSVGElement>(null)
  const [data, setData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedNode, setSelectedNode] = useState<Node | null>(null)
  const [yearFilter, setYearFilter] = useState<{ min: number | null; max: number | null }>({ min: null, max: null })
  const [citationThreshold, setCitationThreshold] = useState(0)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [showHelpModal, setShowHelpModal] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchGraphData()
  }, [projectId])

  useEffect(() => {
    if (data && data.nodes.length > 0) {
      renderGraph()
    }
  }, [data, searchTerm, yearFilter, citationThreshold])

  const fetchGraphData = async () => {
    if (!session?.access_token) return

    setLoading(true)
    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/analytics/projects/${projectId}/citation-graph`,
        {
          headers: {
            'Authorization': `Bearer ${session.access_token}`,
          },
        }
      )

      if (!response.ok) throw new Error('Failed to fetch citation graph')

      const graphData = await response.json()
      setData(graphData)

      // Set initial year filter based on data
      if (graphData.nodes.length > 0) {
        const years = graphData.nodes.map((n: Node) => n.year).filter((y: number | null) => y !== null) as number[]
        if (years.length > 0) {
          setYearFilter({ min: Math.min(...years), max: Math.max(...years) })
        }
      }
    } catch (error: any) {
      console.error('Failed to fetch citation graph:', error)
      toast.error('Failed to load citation network')
    } finally {
      setLoading(false)
    }
  }

  const renderGraph = () => {
    if (!svgRef.current || !data) return

    // Clear previous graph
    d3.select(svgRef.current).selectAll('*').remove()

    // Filter nodes based on search and filters
    const filteredNodes = data.nodes.filter(node => {
      const matchesSearch = searchTerm === '' ||
        node.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
        node.authors.some(a => a.toLowerCase().includes(searchTerm.toLowerCase()))

      const matchesYear = (yearFilter.min === null || node.year === null || node.year >= yearFilter.min) &&
                          (yearFilter.max === null || node.year === null || node.year <= yearFilter.max)

      const matchesCitations = node.citation_count >= citationThreshold

      return matchesSearch && matchesYear && matchesCitations
    })

    const filteredNodeIds = new Set(filteredNodes.map(n => n.id))

    // Filter edges to only include edges between filtered nodes
    const filteredEdges = data.edges.filter(edge => {
      const sourceId = typeof edge.source === 'string' ? edge.source : edge.source.id
      const targetId = typeof edge.target === 'string' ? edge.target : edge.target.id
      return filteredNodeIds.has(sourceId) && filteredNodeIds.has(targetId)
    })

    if (filteredNodes.length === 0) {
      // Show empty state
      const svg = d3.select(svgRef.current)
      const width = svgRef.current.clientWidth
      const height = svgRef.current.clientHeight

      svg.append('text')
        .attr('x', width / 2)
        .attr('y', height / 2)
        .attr('text-anchor', 'middle')
        .attr('fill', '#9CA3AF')
        .attr('font-size', '16px')
        .text('No papers match the current filters')

      return
    }

    // Dimensions
    const width = svgRef.current.clientWidth
    const height = svgRef.current.clientHeight

    const svg = d3.select(svgRef.current)
      .attr('width', width)
      .attr('height', height)

    // Add zoom behavior
    const g = svg.append('g')

    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform)
      })

    svg.call(zoom)

    // Create force simulation
    const simulation = d3.forceSimulation<Node>(filteredNodes)
      .force('link', d3.forceLink<Node, Edge>(filteredEdges)
        .id((d) => d.id)
        .distance(100))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(30))

    // Color scale based on year
    const years = filteredNodes.map(n => n.year).filter(y => y !== null) as number[]
    const colorScale = d3.scaleSequential(d3.interpolateTurbo)
      .domain([Math.min(...years) || 2000, Math.max(...years) || 2024])

    // Draw edges
    const link = g.append('g')
      .selectAll('line')
      .data(filteredEdges)
      .join('line')
      .attr('stroke', '#4B5563')
      .attr('stroke-opacity', 0.4)
      .attr('stroke-width', 1)
      .attr('marker-end', 'url(#arrowhead)')

    // Add arrow marker definition
    svg.append('defs').append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '-10 -10 20 20')
      .attr('refX', 20)
      .attr('refY', 0)
      .attr('markerWidth', 8)
      .attr('markerHeight', 8)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M-6,-6 L 0,0 L -6,6')
      .attr('fill', '#4B5563')
      .attr('opacity', 0.4)

    // Draw nodes
    const node = g.append('g')
      .selectAll('circle')
      .data(filteredNodes)
      .join('circle')
      .attr('r', d => Math.sqrt(d.in_degree + 1) * 5 + 5) // Size based on in-degree
      .attr('fill', d => d.year ? colorScale(d.year) : '#6B7280')
      .attr('stroke', '#1F2937')
      .attr('stroke-width', 2)
      .attr('opacity', 0.9)
      .style('cursor', 'pointer')
      .on('click', (event, d) => {
        event.stopPropagation()
        setSelectedNode(d)
      })
      .on('mouseover', function(event, d) {
        d3.select(this)
          .attr('stroke', '#EC4899')
          .attr('stroke-width', 3)

        // Show tooltip
        d3.select('body').append('div')
          .attr('class', 'citation-tooltip')
          .style('position', 'absolute')
          .style('background', 'rgba(17, 24, 39, 0.95)')
          .style('color', 'white')
          .style('padding', '12px')
          .style('border-radius', '8px')
          .style('border', '1px solid #374151')
          .style('pointer-events', 'none')
          .style('font-size', '14px')
          .style('max-width', '300px')
          .style('z-index', '1000')
          .style('box-shadow', '0 4px 6px rgba(0, 0, 0, 0.3)')
          .html(`
            <div style="font-weight: 600; margin-bottom: 8px;">${d.title}</div>
            <div style="color: #9CA3AF; font-size: 12px; margin-bottom: 4px;">
              ${d.authors.slice(0, 3).join(', ')}${d.authors.length > 3 ? ' et al.' : ''}
            </div>
            <div style="color: #9CA3AF; font-size: 12px;">
              ${d.year || 'Unknown year'} • ${d.citation_count} citations • ${d.in_degree} internal citations
            </div>
          `)
          .style('left', (event.pageX + 10) + 'px')
          .style('top', (event.pageY - 28) + 'px')

        d3.select(this).attr('data-tooltip', 'true')
      })
      .on('mouseout', function() {
        d3.select(this)
          .attr('stroke', '#1F2937')
          .attr('stroke-width', 2)

        d3.selectAll('.citation-tooltip').remove()
      })
      .call(d3.drag<SVGCircleElement, Node>()
        .on('start', (event, d: Node) => {
          if (!event.active) simulation.alphaTarget(0.3).restart()
          d.fx = d.x
          d.fy = d.y
        })
        .on('drag', (event, d: Node) => {
          d.fx = event.x
          d.fy = event.y
        })
        .on('end', (event, d: Node) => {
          if (!event.active) simulation.alphaTarget(0)
          d.fx = null
          d.fy = null
        }) as any)

    // Add labels for influential nodes (in-degree > 2)
    const label = g.append('g')
      .selectAll('text')
      .data(filteredNodes.filter(d => d.in_degree > 2))
      .join('text')
      .text(d => d.title.length > 30 ? d.title.substring(0, 30) + '...' : d.title)
      .attr('font-size', '10px')
      .attr('fill', '#D1D5DB')
      .attr('text-anchor', 'middle')
      .attr('dy', -15)
      .attr('pointer-events', 'none')

    // Update positions on each tick
    simulation.on('tick', () => {
      link
        .attr('x1', d => (d.source as Node).x || 0)
        .attr('y1', d => (d.source as Node).y || 0)
        .attr('x2', d => (d.target as Node).x || 0)
        .attr('y2', d => (d.target as Node).y || 0)

      node
        .attr('cx', d => d.x || 0)
        .attr('cy', d => d.y || 0)

      label
        .attr('x', d => d.x || 0)
        .attr('y', d => d.y || 0)
    })

    // Click on background to deselect
    svg.on('click', () => {
      setSelectedNode(null)
    })
  }

  const toggleFullscreen = () => {
    if (!containerRef.current) return

    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen()
      setIsFullscreen(true)
    } else {
      document.exitFullscreen()
      setIsFullscreen(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent"></div>
      </div>
    )
  }

  if (!data || data.nodes.length === 0) {
    return (
      <div className="bg-neutral-900/30 rounded-lg border border-neutral-800/50 p-8 text-center">
        <svg className="h-16 w-16 text-neutral-600 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
        </svg>
        <p className="text-neutral-400 mb-2">No citation data available</p>
        <p className="text-sm text-neutral-500">Upload documents with citation metadata to see the citation network</p>
      </div>
    )
  }

  const years = data.nodes.map(n => n.year).filter(y => y !== null) as number[]
  const minYear = years.length > 0 ? Math.min(...years) : 2000
  const maxYear = years.length > 0 ? Math.max(...years) : 2024

  return (
    <div ref={containerRef} className="space-y-4">
      {/* Metrics Overview */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-neutral-900/50 rounded-lg p-4 border border-neutral-800">
          <div className="text-sm text-neutral-400 font-mono mb-1">Total Papers</div>
          <div className="text-2xl font-bold text-neutral-50">{data.metrics.total_papers}</div>
        </div>
        <div className="bg-neutral-900/50 rounded-lg p-4 border border-neutral-800">
          <div className="text-sm text-neutral-400 font-mono mb-1">Total Citations</div>
          <div className="text-2xl font-bold text-neutral-50">{data.metrics.total_citations}</div>
        </div>
        <div className="bg-neutral-900/50 rounded-lg p-4 border border-neutral-800">
          <div className="text-sm text-neutral-400 font-mono mb-1">Avg Citations</div>
          <div className="text-2xl font-bold text-neutral-50">{data.metrics.avg_citations_per_paper}</div>
        </div>
        <div className="bg-neutral-900/50 rounded-lg p-4 border border-neutral-800">
          <div className="text-sm text-neutral-400 font-mono mb-1">Internal Links</div>
          <div className="text-2xl font-bold text-neutral-50">{data.metrics.total_internal_citations}</div>
        </div>
      </div>

      {/* Controls */}
      <div className="bg-neutral-900/50 rounded-lg p-4 border border-neutral-800 space-y-4">
        {/* Search */}
        <div className="relative">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-neutral-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by title or author..."
            className="w-full pl-10 pr-10 py-2 bg-neutral-950 border border-neutral-700 rounded-lg text-neutral-50 placeholder-neutral-500 focus:outline-none focus:ring-2 focus:ring-cyan-600 focus:border-transparent transition-colors"
          />
          {searchTerm && (
            <button
              onClick={() => setSearchTerm('')}
              className="absolute right-3 top-1/2 transform -translate-y-1/2 text-neutral-400 hover:text-neutral-50 transition-colors"
            >
              <XMarkIcon className="h-5 w-5" />
            </button>
          )}
        </div>

        {/* Filters */}
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="block text-sm text-neutral-400 font-mono mb-2">Min Year: {yearFilter.min || minYear}</label>
            <input
              type="range"
              min={minYear}
              max={maxYear}
              value={yearFilter.min || minYear}
              onChange={(e) => setYearFilter(prev => ({ ...prev, min: parseInt(e.target.value) }))}
              className="w-full accent-cyan-600"
            />
          </div>
          <div>
            <label className="block text-sm text-neutral-400 font-mono mb-2">Max Year: {yearFilter.max || maxYear}</label>
            <input
              type="range"
              min={minYear}
              max={maxYear}
              value={yearFilter.max || maxYear}
              onChange={(e) => setYearFilter(prev => ({ ...prev, max: parseInt(e.target.value) }))}
              className="w-full accent-cyan-600"
            />
          </div>
          <div>
            <label className="block text-sm text-neutral-400 font-mono mb-2">Min Citations: {citationThreshold}</label>
            <input
              type="range"
              min={0}
              max={Math.max(...data.nodes.map(n => n.citation_count))}
              value={citationThreshold}
              onChange={(e) => setCitationThreshold(parseInt(e.target.value))}
              className="w-full accent-cyan-600"
            />
          </div>
        </div>

        {/* Reset, Help & Fullscreen */}
        <div className="flex justify-between items-center">
          <button
            onClick={() => {
              setSearchTerm('')
              setYearFilter({ min: minYear, max: maxYear })
              setCitationThreshold(0)
            }}
            className="px-4 py-2 text-sm bg-neutral-700 text-neutral-300 font-semibold rounded hover:bg-neutral-600 transition-colors"
          >
            Reset Filters
          </button>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowHelpModal(true)}
              className="px-4 py-2 text-sm bg-cyan-600/20 text-cyan-400 font-semibold rounded hover:bg-cyan-600/30 transition-colors flex items-center gap-2 border border-cyan-600/30"
              title="How to use this visualization"
            >
              <QuestionMarkCircleIcon className="h-4 w-4" />
              How to Use
            </button>
            <button
              onClick={toggleFullscreen}
              className="px-4 py-2 text-sm bg-neutral-700 text-neutral-300 font-semibold rounded hover:bg-neutral-600 transition-colors flex items-center gap-2"
            >
              {isFullscreen ? <ArrowsPointingInIcon className="h-4 w-4" /> : <ArrowsPointingOutIcon className="h-4 w-4" />}
              {isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
            </button>
          </div>
        </div>
      </div>

      {/* Graph Visualization */}
      <div className="bg-neutral-950 rounded-lg border border-neutral-800 overflow-hidden" style={{ height: isFullscreen ? '90vh' : '600px' }}>
        <svg ref={svgRef} className="w-full h-full"></svg>
      </div>

      {/* Selected Node Details */}
      {selectedNode && (
        <div className="bg-neutral-900/50 rounded-lg p-6 border border-neutral-800">
          <div className="flex justify-between items-start mb-4">
            <h3 className="text-lg font-serif font-semibold text-neutral-50">{selectedNode.title}</h3>
            <button onClick={() => setSelectedNode(null)} className="text-neutral-400 hover:text-neutral-50 transition-colors">
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex gap-2">
              <span className="text-neutral-400 font-mono">Authors:</span>
              <span className="text-neutral-300">{selectedNode.authors.join(', ') || 'Unknown'}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-neutral-400 font-mono">Year:</span>
              <span className="text-neutral-300">{selectedNode.year || 'Unknown'}</span>
            </div>
            {selectedNode.journal && (
              <div className="flex gap-2">
                <span className="text-neutral-400 font-mono">Journal:</span>
                <span className="text-neutral-300">{selectedNode.journal}</span>
              </div>
            )}
            <div className="flex gap-2">
              <span className="text-neutral-400 font-mono">Total Citations:</span>
              <span className="text-neutral-300">{selectedNode.citation_count}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-neutral-400 font-mono">Citations in Project:</span>
              <span className="text-neutral-300">{selectedNode.in_degree}</span>
            </div>
            {selectedNode.doi && (
              <div className="flex gap-2">
                <span className="text-neutral-400 font-mono">DOI:</span>
                <a href={`https://doi.org/${selectedNode.doi}`} target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:underline">
                  {selectedNode.doi}
                </a>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Most Influential Papers */}
      {data.metrics.most_influential_papers.length > 0 && (
        <div className="bg-neutral-900/50 rounded-lg p-6 border border-neutral-800">
          <h3 className="text-lg font-serif font-semibold text-neutral-50 mb-4">Most Influential Papers in Project</h3>
          <div className="space-y-2">
            {data.metrics.most_influential_papers.map((paper, idx) => (
              <div key={paper.id} className="flex items-start gap-3 text-sm">
                <span className="text-neutral-500 font-mono">{idx + 1}.</span>
                <div className="flex-1">
                  <div className="text-neutral-300">{paper.title}</div>
                  <div className="text-neutral-500 text-xs font-mono">{paper.in_degree} citations within project</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Help Modal */}
      {showHelpModal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4" onClick={() => setShowHelpModal(false)}>
          <div className="bg-neutral-950 rounded-lg border border-cyan-600/30 max-w-2xl w-full max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            {/* Header */}
            <div className="bg-cyan-900/20 px-6 py-4 border-b border-cyan-600/30 flex items-center justify-between sticky top-0">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 bg-cyan-600/20 rounded-lg flex items-center justify-center">
                  <QuestionMarkCircleIcon className="h-6 w-6 text-cyan-400" />
                </div>
                <h3 className="text-xl font-serif font-semibold text-neutral-50">How to Use the Citation Network</h3>
              </div>
              <button onClick={() => setShowHelpModal(false)} className="text-neutral-400 hover:text-neutral-50 transition-colors">
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            {/* Content */}
            <div className="p-6 space-y-6">
              {/* What is this? */}
              <div>
                <h4 className="text-lg font-semibold text-cyan-400 mb-3">What is the Citation Network?</h4>
                <p className="text-gray-300 leading-relaxed">
                  The Citation Network is an interactive visualization that shows how papers in your project cite each other.
                  Each circle (node) represents a research paper, and each line (edge) represents a citation relationship between papers.
                </p>
              </div>

              {/* Understanding the Visualization */}
              <div>
                <h4 className="text-lg font-semibold text-cyan-400 mb-3">Understanding the Visualization</h4>
                <div className="space-y-3">
                  <div className="flex items-start gap-3">
                    <div className="h-8 w-8 rounded-full bg-pink-500/20 border-2 border-pink-500 shrink-0 mt-0.5"></div>
                    <div>
                      <div className="font-medium text-white">Nodes (Circles)</div>
                      <p className="text-sm text-gray-400">Each node represents a paper. Larger nodes = more citations. Darker color = more influence in the network.</p>
                    </div>
                  </div>
                  <div className="flex items-start gap-3">
                    <div className="h-0.5 w-8 bg-gray-600 shrink-0 mt-4"></div>
                    <div>
                      <div className="font-medium text-white">Edges (Lines)</div>
                      <p className="text-sm text-gray-400">Lines connecting nodes show citation relationships. An edge from Paper A to Paper B means Paper A cites Paper B.</p>
                    </div>
                  </div>
                  <div className="flex items-start gap-3">
                    <div className="text-xl text-gray-300 shrink-0">📍</div>
                    <div>
                      <div className="font-medium text-white">Node Position</div>
                      <p className="text-sm text-gray-400">Papers that cite each other tend to cluster together. Isolated nodes are papers with no internal citations.</p>
                    </div>
                  </div>
                </div>
              </div>

              {/* How to Interact */}
              <div>
                <h4 className="text-lg font-semibold text-cyan-400 mb-3">How to Interact</h4>
                <div className="space-y-2">
                  <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700">
                    <div className="font-medium text-white mb-1">🖱️ Click a Node</div>
                    <p className="text-sm text-gray-400">Click any paper to view detailed information including title, authors, year, journal, and citation counts.</p>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700">
                    <div className="font-medium text-white mb-1">🖐️ Drag Nodes</div>
                    <p className="text-sm text-gray-400">Click and drag nodes to rearrange the network layout. The simulation will adjust nearby nodes automatically.</p>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700">
                    <div className="font-medium text-white mb-1">🔍 Zoom & Pan</div>
                    <p className="text-sm text-gray-400">Use your mouse wheel to zoom in/out. Click and drag the background to pan around the network.</p>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700">
                    <div className="font-medium text-white mb-1">🔎 Search</div>
                    <p className="text-sm text-gray-400">Use the search bar to filter papers by title or author name. The network updates in real-time.</p>
                  </div>
                </div>
              </div>

              {/* Using Filters */}
              <div>
                <h4 className="text-lg font-semibold text-cyan-400 mb-3">Using Filters</h4>
                <div className="space-y-2 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="text-gray-400">📅</span>
                    <span className="text-white font-medium">Year Range:</span>
                    <span className="text-gray-400">Show only papers published between specific years</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-gray-400">📊</span>
                    <span className="text-white font-medium">Min Citations:</span>
                    <span className="text-gray-400">Filter out papers with fewer than X citations</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-gray-400">🔄</span>
                    <span className="text-white font-medium">Reset Filters:</span>
                    <span className="text-gray-400">Click "Reset Filters" to clear all filters and show all papers</span>
                  </div>
                </div>
              </div>

              {/* Understanding Metrics */}
              <div>
                <h4 className="text-lg font-semibold text-cyan-400 mb-3">Understanding the Metrics</h4>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700">
                    <div className="font-medium text-white mb-1">Total Papers</div>
                    <p className="text-gray-400">Number of papers currently visible in the network</p>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700">
                    <div className="font-medium text-white mb-1">Total Citations</div>
                    <p className="text-gray-400">Sum of all external citations across all papers</p>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700">
                    <div className="font-medium text-white mb-1">Avg Citations</div>
                    <p className="text-gray-400">Average number of citations per paper</p>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700">
                    <div className="font-medium text-white mb-1">Internal Links</div>
                    <p className="text-gray-400">Number of citation connections between papers in your project</p>
                  </div>
                </div>
              </div>

              {/* Tips */}
              <div className="bg-cyan-900/20 border border-cyan-600/30 rounded-lg p-4">
                <h4 className="text-lg font-semibold text-cyan-400 mb-2">💡 Pro Tips</h4>
                <ul className="space-y-1.5 text-sm text-gray-300">
                  <li>• Papers with more connections are usually more influential in your research area</li>
                  <li>• Isolated papers might represent emerging topics or niche areas</li>
                  <li>• Clusters of connected papers often represent related sub-topics</li>
                  <li>• Use fullscreen mode for better viewing of large networks</li>
                  <li>• The "Most Influential Papers" section shows which papers are most cited within your project</li>
                </ul>
              </div>
            </div>

            {/* Footer */}
            <div className="bg-neutral-900/50 px-6 py-4 border-t border-neutral-800 flex justify-end sticky bottom-0">
              <button
                onClick={() => setShowHelpModal(false)}
                className="px-6 py-2 bg-cyan-600 text-white font-semibold rounded-lg hover:bg-cyan-700 transition-colors"
              >
                Got it!
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
