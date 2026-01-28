import { useEffect, useRef } from 'react'
import * as d3 from 'd3'

interface SynthesisQuestion {
  question: string
  category: string
  icon: string
  related_papers: string[]
}

interface MindMapProps {
  questions: SynthesisQuestion[]
}

interface HierarchyNode {
  name: string
  category?: string
  type: 'root' | 'category' | 'question' | 'paper'
  children?: HierarchyNode[]
}

export default function SynthesisQuestionsMindMap({ questions }: MindMapProps) {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (!svgRef.current || questions.length === 0) return

    renderMindMap()
  }, [questions])

  const renderMindMap = () => {
    if (!svgRef.current) return

    // Clear previous visualization
    d3.select(svgRef.current).selectAll('*').remove()

    // Prepare hierarchical data
    const categoryInfo: Record<string, { title: string; icon: string; color: string }> = {
      conflict: { title: 'Conflicting Findings', icon: '⚡', color: '#fb923c' },
      gap: { title: 'Research Gaps', icon: '🔍', color: '#a78bfa' },
      pattern: { title: 'Methodological Patterns', icon: '🔬', color: '#60a5fa' },
      positioning: { title: 'Research Positioning', icon: '🎯', color: '#34d399' }
    }

    // Group questions by category
    const questionsByCategory = questions.reduce((acc, q) => {
      if (!acc[q.category]) acc[q.category] = []
      acc[q.category].push(q)
      return acc
    }, {} as Record<string, SynthesisQuestion[]>)

    // Build hierarchy
    const root: HierarchyNode = {
      name: 'Synthesis Questions',
      type: 'root',
      children: Object.entries(questionsByCategory).map(([category, categoryQuestions]) => ({
        name: categoryInfo[category]?.title || category,
        category: category,
        type: 'category' as const,
        children: categoryQuestions.map(q => ({
          name: q.question.length > 80 ? q.question.substring(0, 80) + '...' : q.question,
          type: 'question' as const,
          children: q.related_papers.slice(0, 3).map(paper => ({
            name: paper.length > 40 ? paper.substring(0, 40) + '...' : paper,
            type: 'paper' as const
          }))
        }))
      }))
    }

    // Dimensions
    const width = 1200
    const height = 800
    const margin = { top: 20, right: 120, bottom: 20, left: 120 }

    const svg = d3.select(svgRef.current)
      .attr('width', width)
      .attr('height', height)
      .attr('viewBox', `0 0 ${width} ${height}`)

    const g = svg.append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`)

    // Create tree layout
    const treeLayout = d3.tree<HierarchyNode>()
      .size([height - margin.top - margin.bottom, width - margin.left - margin.right])

    const hierarchy = d3.hierarchy(root)
    const treeData = treeLayout(hierarchy)

    // Color scale for categories
    const getNodeColor = (d: d3.HierarchyPointNode<HierarchyNode>) => {
      if (d.data.type === 'root') return '#3b82f6'
      if (d.data.type === 'category') {
        const category = d.data.category || ''
        return categoryInfo[category]?.color || '#6b7280'
      }
      if (d.data.type === 'question') return '#10b981'
      return '#6b7280'
    }

    const getNodeSize = (d: d3.HierarchyPointNode<HierarchyNode>) => {
      if (d.data.type === 'root') return 10
      if (d.data.type === 'category') return 8
      if (d.data.type === 'question') return 6
      return 4
    }

    // Add zoom behavior
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.5, 3])
      .on('zoom', (event) => {
        g.attr('transform', event.transform)
      })

    svg.call(zoom)

    // Draw links
    g.selectAll('.link')
      .data(treeData.links())
      .enter()
      .append('path')
      .attr('class', 'link')
      .attr('d', d3.linkHorizontal<any, d3.HierarchyPointNode<HierarchyNode>>()
        .x(d => d.y)
        .y(d => d.x)
      )
      .style('fill', 'none')
      .style('stroke', '#4b5563')
      .style('stroke-width', d => {
        if (d.source.data.type === 'root') return 3
        if (d.source.data.type === 'category') return 2
        return 1
      })
      .style('stroke-opacity', 0.4)

    // Draw nodes
    const node = g.selectAll('.node')
      .data(treeData.descendants())
      .enter()
      .append('g')
      .attr('class', 'node')
      .attr('transform', d => `translate(${d.y},${d.x})`)

    // Add circles
    node.append('circle')
      .attr('r', d => getNodeSize(d))
      .style('fill', d => getNodeColor(d))
      .style('stroke', '#1f2937')
      .style('stroke-width', 2)
      .style('cursor', d => d.data.type !== 'paper' ? 'pointer' : 'default')
      .on('mouseenter', function(event, d) {
        d3.select(this)
          .transition()
          .duration(200)
          .attr('r', getNodeSize(d) * 1.5)
      })
      .on('mouseleave', function(event, d) {
        d3.select(this)
          .transition()
          .duration(200)
          .attr('r', getNodeSize(d))
      })

    // Add labels
    node.append('text')
      .attr('dy', '0.31em')
      .attr('x', d => d.children ? -15 : 15)
      .style('text-anchor', d => d.children ? 'end' : 'start')
      .style('font-size', d => {
        if (d.data.type === 'root') return '16px'
        if (d.data.type === 'category') return '14px'
        if (d.data.type === 'question') return '12px'
        return '10px'
      })
      .style('fill', '#e5e7eb')
      .style('font-weight', d => d.data.type === 'root' || d.data.type === 'category' ? 'bold' : 'normal')
      .text(d => d.data.name)
      .each(function(d) {
        // Wrap long text
        const text = d3.select(this)
        const words = d.data.name.split(/\s+/)
        const lineHeight = 1.1
        const maxWidth = 200

        if (d.data.type === 'question' && words.length > 10) {
          text.text('')
          let line: string[] = []
          let lineNumber = 0

          words.forEach(word => {
            line.push(word)
            const testLine = line.join(' ')
            const testWidth = testLine.length * 6 // Approximate character width

            if (testWidth > maxWidth && line.length > 1) {
              line.pop()
              text.append('tspan')
                .attr('x', d.children ? -15 : 15)
                .attr('dy', lineNumber === 0 ? 0 : `${lineHeight}em`)
                .text(line.join(' '))
              line = [word]
              lineNumber++
            }
          })

          if (line.length > 0) {
            text.append('tspan')
              .attr('x', d.children ? -15 : 15)
              .attr('dy', lineNumber === 0 ? 0 : `${lineHeight}em`)
              .text(line.join(' '))
          }
        }
      })

    // Add legend
    const legend = svg.append('g')
      .attr('transform', `translate(${width - 200}, 20)`)

    const legendData = [
      { type: 'Root', color: '#3b82f6', size: 10 },
      { type: 'Category', color: '#a78bfa', size: 8 },
      { type: 'Question', color: '#10b981', size: 6 },
      { type: 'Paper', color: '#6b7280', size: 4 }
    ]

    legendData.forEach((item, i) => {
      const legendRow = legend.append('g')
        .attr('transform', `translate(0, ${i * 25})`)

      legendRow.append('circle')
        .attr('r', item.size)
        .style('fill', item.color)

      legendRow.append('text')
        .attr('x', 20)
        .attr('dy', '0.32em')
        .style('font-size', '12px')
        .style('fill', '#9ca3af')
        .text(item.type)
    })

    // Add instructions
    svg.append('text')
      .attr('x', 20)
      .attr('y', height - 10)
      .style('font-size', '12px')
      .style('fill', '#6b7280')
      .text('💡 Scroll to zoom • Drag to pan • Hover to enlarge nodes')
  }

  if (questions.length === 0) {
    return (
      <div className="bg-surface/50 rounded-lg border border-border-base p-8 text-center">
        <p className="text-text-tertiary">
          No synthesis questions available. Generate insights first to see the mind map.
        </p>
      </div>
    )
  }

  return (
    <div className="bg-surface/50 rounded-lg border border-border-base p-4 overflow-hidden">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold text-text-secondary">Question Relationships Mind Map</h4>
        <p className="text-xs text-text-muted">
          Visual exploration of synthesis questions, categories, and related papers
        </p>
      </div>
      <div className="bg-bg-base rounded-lg overflow-auto">
        <svg ref={svgRef} className="w-full" style={{ minHeight: '800px' }}></svg>
      </div>
    </div>
  )
}
