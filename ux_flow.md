Recommended User Flow: Documents-First (Primary)

 Flow Diagram

 1. Create Project
    ↓
 2. Upload Documents (1+ papers)
    ↓ Auto-triggers analysis for each
 3. Document Analysis Completes
    - Extracts: claims, methods, findings
    - IF insights exist: Auto-regenerates
    ↓
 4. Generate Insights (Manual)
    - Cross-paper analysis using LangGraph data
    - Research gaps, themes, patterns
    ↓
 5. Explore Literature (Optional)
    - Chat with RAG
    - Citation network
    - Paper recommendations
    ↓
 6. Upload Draft
    ↓ Auto-triggers analysis
 7. Draft Analysis Completes
    - Citation suggestions (uses document_claims)
    - Coverage gaps (uses documents)
    - Reviewer feedback
    ↓
 8. View Literature Compass (Manual)
    - Visual exploration
    - Uses insights + draft analysis
    ↓
 9. Iterate
    - More documents → insights auto-regenerate
    - Draft revisions → re-analyze

 Why Documents-First is Optimal

 Technical:
 - ✅ Citation suggestions work (document_claims populated)
 - ✅ Coverage gaps suggest specific papers from library
 - ✅ Insights ready for compass visualization
 - ✅ All features provide maximum value
 - ✅ Auto-regeneration triggers work correctly

 User Experience:
 - ✅ Natural academic workflow (gather literature before writing)
 - ✅ Insights help understand gaps before drafting
 - ✅ Research questions guide draft structure
 - ✅ Draft analysis builds on knowledge base

 Cost Efficiency:
 - ✅ No redundant processing (each document analyzed once)
 - ✅ Insights auto-regenerate using stored analysis
 - ✅ Draft analysis uses cached embeddings


  ---
 Alternative Flow: Draft-First (Secondary)

 Flow Diagram

 1. Create Project
    ↓
 2. Upload Draft
    ↓ Auto-triggers analysis
 3. Draft Analysis Completes
    - Claims extracted
    - Citation suggestions: EMPTY
    - Coverage gaps: NO paper suggestions
    - Feedback: Generic only
    ↓
 4. UI Prompt: "Upload documents for citations"
    ↓
 5. Upload Documents
    ↓ Auto-triggers analysis
 6. Document Analysis Completes
    ↓
 7. Re-analyze Draft (Auto)
    - Citations: NOW POPULATED
    - Gaps: NOW has suggestions
    ↓
 8. Generate Insights → Continue primary flow

 Edge Case Mitigations

 1. UI/UX Guidance (High Priority)

 Empty State - No Documents:
 📚 Get Started

 Step 1: Upload Research Papers
 Upload papers related to your research to build your knowledge base.

 [Upload Documents Button]

 Why start with papers?
 ✓ Get citation suggestions for your draft
 ✓ Identify research gaps and themes
 ✓ Find relevant methodologies

 Draft Uploaded Without Documents:
 ⚠️ Upload research papers to get citation suggestions and coverage analysis
 [Upload Documents Button]

 Draft Analysis Results - No Citations:
 Citation Suggestions: 0 found

 ⚠️ No documents uploaded yet. Upload research papers to see suggestions.
 [Upload Documents Button]