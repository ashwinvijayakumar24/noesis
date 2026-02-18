Implement the following plan:                                                                                                                                 
                                                                                                                                                                
  # Production Deployment Plan - Noesis Updates to AWS + Vercel                                                                                                 
                                                                                                                                                                
  ## Overview                                                                                                                                                   
                                                                                                                                                                
  Deploy all recent changes to production environment:                                                                                                          
  - **Frontend**: Vercel (https://noesis.is)                                                                                                                    
  - **Backend**: AWS EC2 + Docker Compose (https://api.noesis.is)                                                                                               
  - **Database**: Supabase (cloud, no changes needed)                                                                                                           
                                                                                                                                                                
  ## Pre-Deployment Checklist                                                                                                                                   
                                                                                                                                                                
  ### Changes to Deploy                                                                                                                                         
                                                                                                                                                                
  **New Features:**                                                                                                                                             
  - ✅ Celery background task processing (Redis + Celery worker containers)                                                                                     
  - ✅ Draft analysis with LangGraph workflows                                                                                                                  
  - ✅ Citation management and BibTeX export                                                                                                                    
  - ✅ PDF export for draft analysis                                                                                                                            
  - ✅ Toast notifications for insights updates                                                                                                                 
  - ✅ UI improvements (colored icons, solid badges, better styling)                                                                                            
  - ✅ Fixed draft upload bug (import error)                                                                                                                    
  - ✅ Multiple bug fixes and UX enhancements                                                                                                                   
                                                                                                                                                                
  **Modified Containers:**                                                                                                                                      
  - backend (FastAPI): Code updates                                                                                                                             
  - celery-worker: NEW container for background tasks                                                                                                           
  - redis: NEW container for task queue                                                                                                                         
  - grobid: No changes                                                                                                                                          
  - frontend: Build updates (Vite)                                                                                                                              
                                                                                                                                                                
  **Configuration Changes:**                                                                                                                                    
  - docker-compose.prod.yml: Updated with Redis and Celery                                                                                                      
  - Environment variables: No new vars needed                                                                                                                   
  - CORS: Already configured for api.noesis.is                                                                                                                  
                                                                                                                                                                
  ---                                                                                                                                                           
                                                                                                                                                                
  ## Phase 1: Git Commit & Push (10-15 minutes)                                                                                                                 
                                                                                                                                                                
  ### Step 1.1: Review Changes                                                                                                                                  
                                                                                                                                                                
  ```bash                                                                                                                                                       
  cd /Applications/Ashwin/Programming/Personal\ Projects/startup/noesis                                                                                         
                                                                                                                                                                
  # Check current branch                                                                                                                                        
  git branch                                                                                                                                                    
                                                                                                                                                                
  # Review all changes                                                                                                                                          
  git status                                                                                                                                                    
                                                                                                                                                                
  # Review specific changes (optional)                                                                                                                          
  git diff services/backend/                                                                                                                                    
  git diff services/frontend/                                                                                                                                   
  ```                                                                                                                                                           
                                                                                                                                                                
  ### Step 1.2: Commit All Changes                                                                                                                              
                                                                                                                                                                
  **Strategy**: Create a single comprehensive commit with all updates                                                                                           
                                                                                                                                                                
  ```bash                                                                                                                                                       
  # Stage all changes                                                                                                                                           
  git add .                                                                                                                                                     
                                                                                                                                                                
  # Create commit with detailed message                                                                                                                         
  git commit -m "Production update: Draft analysis, citations, UI improvements                                                                                  
                                                                                                                                                                
  Features:                                                                                                                                                     
  - Add Celery background task processing with Redis                                                                                                            
  - Implement draft analysis with LangGraph workflows                                                                                                           
  - Add citation management and BibTeX export                                                                                                                   
  - Add PDF export for draft analysis                                                                                                                           
  - Add toast notifications for insights updates                                                                                                                
  - Fix draft upload import error                                                                                                                               
                                                                                                                                                                
  UI Improvements:                                                                                                                                              
  - Add colored icon borders for better visual hierarchy                                                                                                        
  - Change status badges to solid colors (non-neon)                                                                                                             
  - Increase tab sizes for better prominence                                                                                                                    
  - Update Export BibTeX button styling                                                                                                                         
  - Multiple styling refinements                                                                                                                                
                                                                                                                                                                
  Containers:                                                                                                                                                   
  - Add Redis container for Celery task queue                                                                                                                   
  - Add Celery worker container for background processing                                                                                                       
  - Update docker-compose.prod.yml with resource limits                                                                                                         
                                                                                                                                                                
  Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"                                                                                                    
  ```                                                                                                                                                           
                                                                                                                                                                
  ### Step 1.3: Push to GitHub                                                                                                                                  
                                                                                                                                                                
  ```bash                                                                                                                                                       
  # Push to master (or main)                                                                                                                                    
  git push origin master                                                                                                                                        
                                                                                                                                                                
  # Verify push succeeded                                                                                                                                       
  git log --oneline -1                                                                                                                                          
  ```                                                                                                                                                           
                                                                                                                                                                
  ---                                                                                                                                                           
                                                                                                                                                                
  ## Phase 2: Deploy Frontend to Vercel (5-10 minutes)                                                                                                          
                                                                                                                                                                
  ### Step 2.1: Verify Build Locally (Optional)                                                                                                                 
                                                                                                                                                                
  ```bash                                                                                                                                                       
  cd services/frontend                                                                                                                                          
                                                                                                                                                                
  # Test production build locally                                                                                                                               
  npm run build                                                                                                                                                 
                                                                                                                                                                
  # Check for build errors                                                                                                                                      
  # If successful, continue to deployment                                                                                                                       
  ```                                                                                                                                                           
                                                                                                                                                                
  ### Step 2.2: Deploy to Vercel                                                                                                                                
                                                                                                                                                                
  **Option A: Automatic Deployment (Recommended)**                                                                                                              
  - Vercel auto-deploys on git push to master                                                                                                                   
  - Check Vercel dashboard for deployment status                                                                                                                
  - URL: https://vercel.com/dashboard                                                                                                                           
                                                                                                                                                                
  **Option B: Manual Deployment**                                                                                                                               
  ```bash                                                                                                                                                       
  cd services/frontend                                                                                                                                          
                                                                                                                                                                
  # Install Vercel CLI if not installed                                                                                                                         
  npm install -g vercel                                                                                                                                         
                                                                                                                                                                
  # Deploy to production                                                                                                                                        
  vercel --prod                                                                                                                                                 
                                                                                                                                                                
  # Follow prompts (should remember previous configuration)                                                                                                     
  ```                                                                                                                                                           
                                                                                                                                                                
  ### Step 2.3: Verify Frontend Deployment                                                                                                                      
                                                                                                                                                                
  ```bash                                                                                                                                                       
  # Check deployment status                                                                                                                                     
  curl -I https://noesis.is                                                                                                                                     
                                                                                                                                                                
  # Verify API connection                                                                                                                                       
  # Open https://noesis.is in browser                                                                                                                           
  # Check browser console for errors                                                                                                                            
  # Test login flow                                                                                                                                             
  ```                                                                                                                                                           
                                                                                                                                                                
  ---                                                                                                                                                           
                                                                                                                                                                
  ## Phase 3: Deploy Backend to AWS EC2 (15-20 minutes)                                                                                                         
                                                                                                                                                                
  ### Step 3.1: SSH into EC2 Instance                                                                                                                           
                                                                                                                                                                
  ```bash                                                                                                                                                       
  # Connect to EC2 instance                                                                                                                                     
  ssh -i ~/.ssh/noesis-key.pem ubuntu@<EC2_ELASTIC_IP>                                                                                                          
                                                                                                                                                                
  # Or if you have an alias configured                                                                                                                          
  ssh noesis-prod                                                                                                                                               
  ```                                                                                                                                                           
                                                                                                                                                                
  ### Step 3.2: Pull Latest Code                                                                                                                                
                                                                                                                                                                
  ```bash                                                                                                                                                       
  # Navigate to app directory                                                                                                                                   
  cd ~/noesis                                                                                                                                                   
                                                                                                                                                                
  # Stash any local changes (if any)                                                                                                                            
  git stash                                                                                                                                                     
                                                                                                                                                                
  # Pull latest changes                                                                                                                                         
  git pull origin master                                                                                                                                        
                                                                                                                                                                
  # Verify latest commit                                                                                                                                        
  git log --oneline -1                                                                                                                                          
  ```                                                                                                                                                           
                                                                                                                                                                
  ### Step 3.3: Update Environment Files (If Needed)                                                                                                            
                                                                                                                                                                
  ```bash                                                                                                                                                       
  # Check if .env.prod exists with correct values                                                                                                               
  cd ~/noesis/services/backend                                                                                                                                  
  cat .env.prod                                                                                                                                                 
                                                                                                                                                                
  # Verify critical variables:                                                                                                                                  
  # - SUPABASE_URL                                                                                                                                              
  # - SUPABASE_SERVICE_ROLE_KEY                                                                                                                                 
  # - OPENAI_API_KEY                                                                                                                                            
  # - CORS_ORIGINS=https://noesis.is                                                                                                                            
  # - ENVIRONMENT=production                                                                                                                                    
                                                                                                                                                                
  # If any missing, update:                                                                                                                                     
  nano .env.prod                                                                                                                                                
  ```                                                                                                                                                           
                                                                                                                                                                
  ### Step 3.4: Rebuild and Restart Containers                                                                                                                  
                                                                                                                                                                
  ```bash                                                                                                                                                       
  cd ~/noesis/infra                                                                                                                                             
                                                                                                                                                                
  # Stop all containers                                                                                                                                         
  docker compose -f docker-compose.prod.yml down                                                                                                                
                                                                                                                                                                
  # Remove old images to force rebuild                                                                                                                          
  docker compose -f docker-compose.prod.yml build --no-cache                                                                                                    
                                                                                                                                                                
  # Start all containers                                                                                                                                        
  docker compose -f docker-compose.prod.yml up -d                                                                                                               
                                                                                                                                                                
  # Verify all containers are running                                                                                                                           
  docker compose -f docker-compose.prod.yml ps                                                                                                                  
  ```                                                                                                                                                           
                                                                                                                                                                
  **Expected output:**                                                                                                                                          
  ```                                                                                                                                                           
  NAME                      STATUS              PORTS                                                                                                           
  noesis-backend-prod       Up (healthy)        127.0.0.1:8000->8000/tcp                                                                                        
  noesis-celery-worker-prod Up (healthy)                                                                                                                        
  noesis-grobid-prod        Up (healthy)                                                                                                                        
  noesis-redis-prod         Up (healthy)                                                                                                                        
  ```                                                                                                                                                           
                                                                                                                                                                
  ### Step 3.5: Check Container Logs                                                                                                                            
                                                                                                                                                                
  ```bash                                                                                                                                                       
  # Check backend logs                                                                                                                                          
  docker-compose -f docker-compose.prod.yml logs backend --tail=50                                                                                              
                                                                                                                                                                
  # Check celery worker logs                                                                                                                                    
  docker-compose -f docker-compose.prod.yml logs celery-worker --tail=50                                                                                        
                                                                                                                                                                
  # Check for errors                                                                                                                                            
  docker-compose -f docker-compose.prod.yml logs --tail=100 | grep -i error                                                                                     
  ```                                                                                                                                                           
                                                                                                                                                                
  ### Step 3.6: Verify Health Endpoints                                                                                                                         
                                                                                                                                                                
  ```bash                                                                                                                                                       
  # Test backend health endpoint                                                                                                                                
  curl http://localhost:8000/health                                                                                                                             
                                                                                                                                                                
  # Expected: {"status":"healthy"}                                                                                                                              
                                                                                                                                                                
  # Test from outside (via Nginx)                                                                                                                               
  curl https://api.noesis.is/health                                                                                                                             
  ```                                                                                                                                                           
                                                                                                                                                                
  ---                                                                                                                                                           
                                                                                                                                                                
  ## Phase 4: Verification & Testing (10-15 minutes)                                                                                                            
                                                                                                                                                                
  ### Step 4.1: API Endpoint Tests                                                                                                                              
                                                                                                                                                                
  ```bash                                                                                                                                                       
  # From local machine, test API endpoints                                                                                                                      
                                                                                                                                                                
  # Health check                                                                                                                                                
  curl https://api.noesis.is/health                                                                                                                             
                                                                                                                                                                
  # API docs (should load)                                                                                                                                      
  open https://api.noesis.is/docs                                                                                                                               
                                                                                                                                                                
  # Test CORS headers                                                                                                                                           
  curl -I -X OPTIONS https://api.noesis.is/projects \                                                                                                           
  -H "Origin: https://noesis.is" \                                                                                                                              
  -H "Access-Control-Request-Method: GET"                                                                                                                       
  ```                                                                                                                                                           
                                                                                                                                                                
  ### Step 4.2: Frontend Integration Tests                                                                                                                      
                                                                                                                                                                
  Open https://noesis.is in browser and test:                                                                                                                   
                                                                                                                                                                
  **Authentication:**                                                                                                                                           
  - [ ] Login with existing account                                                                                                                             
  - [ ] Signup with new account                                                                                                                                 
  - [ ] Logout and re-login                                                                                                                                     
                                                                                                                                                                
  **Document Upload:**                                                                                                                                          
  - [ ] Upload a PDF document                                                                                                                                   
  - [ ] Verify document processes successfully                                                                                                                  
  - [ ] Check status changes: Uploaded → Processing → Processed                                                                                                 
  - [ ] View document analysis                                                                                                                                  
                                                                                                                                                                
  **Draft Upload (NEW FEATURE):**                                                                                                                               
  - [ ] Upload a research draft (PDF or DOCX)                                                                                                                   
  - [ ] Verify draft processes successfully                                                                                                                     
  - [ ] View draft analysis with claims, gaps, citations                                                                                                        
  - [ ] Test PDF export functionality                                                                                                                           
  - [ ] Test citation suggestions                                                                                                                               
                                                                                                                                                                
  **Citations (NEW FEATURE):**                                                                                                                                  
  - [ ] Export BibTeX from project                                                                                                                              
  - [ ] Verify BibTeX file downloads correctly                                                                                                                  
                                                                                                                                                                
  **Insights:**                                                                                                                                                 
  - [ ] Navigate to Insights tab                                                                                                                                
  - [ ] Trigger insights analysis                                                                                                                               
  - [ ] Verify toast notification appears when complete                                                                                                         
  - [ ] Check colored icon borders display correctly                                                                                                            
                                                                                                                                                                
  **UI Elements:**                                                                                                                                              
  - [ ] Verify tabs have colored icons (Literature: orange, Insights: yellow, Drafts: purple)                                                                   
  - [ ] Verify status badges show solid colors (not neon)                                                                                                       
  - [ ] Verify Export BibTeX button has proper styling                                                                                                          
  - [ ] Verify document icons have colored borders                                                                                                              
                                                                                                                                                                
  ### Step 4.3: Background Task Verification                                                                                                                    
                                                                                                                                                                
  **Test Celery worker is processing tasks:**                                                                                                                   
                                                                                                                                                                
  On EC2 instance:                                                                                                                                              
  ```bash                                                                                                                                                       
  # Check Celery worker logs for task processing                                                                                                                
  docker-compose -f docker-compose.prod.yml logs celery-worker --tail=100                                                                                       
                                                                                                                                                                
  # Should see task execution logs when uploading documents/drafts                                                                                              
  # Look for: [TASK-NAME] Starting... [TASK-NAME] Complete                                                                                                      
  ```                                                                                                                                                           
                                                                                                                                                                
  ### Step 4.4: Performance Check                                                                                                                               
                                                                                                                                                                
  ```bash                                                                                                                                                       
  # Check container resource usage                                                                                                                              
  docker stats --no-stream                                                                                                                                      
                                                                                                                                                                
  # Verify memory usage is within limits:                                                                                                                       
  # - backend: < 384MB                                                                                                                                          
  # - celery-worker: < 512MB                                                                                                                                    
  # - redis: < 128MB                                                                                                                                            
  # - grobid: < 512MB                                                                                                                                           
  ```                                                                                                                                                           
                                                                                                                                                                
  ### Step 4.5: Error Monitoring                                                                                                                                
                                                                                                                                                                
  ```bash                                                                                                                                                       
  # On EC2, check for errors in last hour                                                                                                                       
  cd ~/noesis/infra                                                                                                                                             
                                                                                                                                                                
  # Backend errors                                                                                                                                              
  docker-compose -f docker-compose.prod.yml logs backend --since 1h | grep -i "error\|exception\|traceback"                                                     
                                                                                                                                                                
  # Celery errors                                                                                                                                               
  docker-compose -f docker-compose.prod.yml logs celery-worker --since 1h | grep -i "error\|exception\|traceback"                                               
  ```                                                                                                                                                           
                                                                                                                                                                
  ---                                                                                                                                                           
                                                                                                                                                                
  ## Phase 5: Post-Deployment Monitoring (Ongoing)                                                                                                              
                                                                                                                                                                
  ### Step 5.1: Set Up Monitoring                                                                                                                               
                                                                                                                                                                
  **On EC2 instance:**                                                                                                                                          
  ```bash                                                                                                                                                       
  # Create monitoring script                                                                                                                                    
  cat > ~/monitor.sh << 'EOF'                                                                                                                                   
  #!/bin/bash                                                                                                                                                   
  cd ~/noesis/infra                                                                                                                                             
  echo "=== Container Status ==="                                                                                                                               
  docker-compose -f docker-compose.prod.yml ps                                                                                                                  
  echo ""                                                                                                                                                       
  echo "=== Resource Usage ==="                                                                                                                                 
  docker stats --no-stream                                                                                                                                      
  echo ""                                                                                                                                                       
  echo "=== Recent Errors ==="                                                                                                                                  
  docker-compose -f docker-compose.prod.yml logs --since 5m | grep -i "error\|exception" | tail -20                                                             
  EOF                                                                                                                                                           
                                                                                                                                                                
  chmod +x ~/monitor.sh                                                                                                                                         
                                                                                                                                                                
  # Run monitoring                                                                                                                                              
  ~/monitor.sh                                                                                                                                                  
  ```                                                                                                                                                           
                                                                                                                                                                
  ### Step 5.2: Setup Log Rotation (If Not Already Done)                                                                                                        
                                                                                                                                                                
  ```bash                                                                                                                                                       
  # Check disk space                                                                                                                                            
  df -h                                                                                                                                                         
                                                                                                                                                                
  # If logs are large, rotate them                                                                                                                              
  docker-compose -f docker-compose.prod.yml logs --tail=0 > /dev/null                                                                                           
  ```                                                                                                                                                           
                                                                                                                                                                
  ### Step 5.3: Verify SSL Certificate                                                                                                                          
                                                                                                                                                                
  ```bash                                                                                                                                                       
  # Check SSL certificate validity                                                                                                                              
  curl -vI https://api.noesis.is 2>&1 | grep -A 5 "SSL certificate"                                                                                             
                                                                                                                                                                
  # Verify auto-renewal is working                                                                                                                              
  sudo certbot renew --dry-run                                                                                                                                  
  ```                                                                                                                                                           
                                                                                                                                                                
  ---                                                                                                                                                           
                                                                                                                                                                
  ## Rollback Plan (Emergency)                                                                                                                                  
                                                                                                                                                                
  If deployment fails or causes issues:                                                                                                                         
                                                                                                                                                                
  ### Quick Rollback                                                                                                                                            
                                                                                                                                                                
  ```bash                                                                                                                                                       
  # On EC2 instance                                                                                                                                             
  cd ~/noesis                                                                                                                                                   
                                                                                                                                                                
  # Revert to previous commit                                                                                                                                   
  git log --oneline -5  # Find previous commit hash                                                                                                             
  git checkout <previous-commit-hash>                                                                                                                           
                                                                                                                                                                
  # Rebuild containers with old code                                                                                                                            
  cd infra                                                                                                                                                      
  docker-compose -f docker-compose.prod.yml down                                                                                                                
  docker-compose -f docker-compose.prod.yml up -d --build                                                                                                       
                                                                                                                                                                
  # Verify rollback                                                                                                                                             
  curl https://api.noesis.is/health                                                                                                                             
  ```                                                                                                                                                           
                                                                                                                                                                
  ### Frontend Rollback                                                                                                                                         
                                                                                                                                                                
  **Vercel Dashboard:**                                                                                                                                         
  1. Go to https://vercel.com/dashboard                                                                                                                         
  2. Select Noesis project                                                                                                                                      
  3. Go to Deployments tab                                                                                                                                      
  4. Find previous successful deployment                                                                                                                        
  5. Click "..." → "Promote to Production"                                                                                                                      
                                                                                                                                                                
  ---                                                                                                                                                           
                                                                                                                                                                
  ## Critical Files Modified                                                                                                                                    
                                                                                                                                                                
  **Infrastructure:**                                                                                                                                           
  - `infra/docker-compose.prod.yml` - Added Redis and Celery containers                                                                                         
  - `infra/docker-compose.yml` - Development container updates                                                                                                  
                                                                                                                                                                
  **Backend (Critical):**                                                                                                                                       
  - `services/backend/app/api/routes/drafts.py` - Fixed import error (line 518)                                                                                 
  - `services/backend/app/api/routes/documents.py` - BibTeX export endpoint                                                                                     
  - `services/backend/app/api/routes/citations.py` - NEW: Citation management                                                                                   
  - `services/backend/app/celery_app.py` - NEW: Celery configuration                                                                                            
  - `services/backend/app/services/draft_processing.py` - NEW: Draft analysis                                                                                   
  - `services/backend/app/services/citation_management.py` - NEW: Citations                                                                                     
  - `services/backend/requirements.txt` - New dependencies                                                                                                      
                                                                                                                                                                
  **Frontend (Critical):**                                                                                                                                      
  - `services/frontend/src/pages/ProjectDetail.tsx` - UI improvements, colored icons                                                                            
  - `services/frontend/src/components/ui/Badge.tsx` - Solid color badges                                                                                        
  - `services/frontend/src/components/ui/Toast.tsx` - NEW: Toast notifications                                                                                  
  - `services/frontend/src/components/InsightsTab/index.tsx` - Toast integration, colored icons                                                                 
  - `services/frontend/src/components/compass/StructureAdvisorTab.tsx` - Redesigned UI                                                                          
  - `services/frontend/tailwind.config.js` - Animation updates                                                                                                  
                                                                                                                                                                
  **Configuration:**                                                                                                                                            
  - `vercel.json` - SPA routing configuration                                                                                                                   
  - `.gitignore` - Updated patterns                                                                                                                             
  - `README.md` - Updated documentation                                                                                                                         
                                                                                                                                                                
  ---                                                                                                                                                           
                                                                                                                                                                
  ## Success Criteria                                                                                                                                           
                                                                                                                                                                
  **Deployment Complete When:**                                                                                                                                 
  - ✅ All git changes committed and pushed                                                                                                                     
  - ✅ Frontend deployed to Vercel (https://noesis.is loads)                                                                                                    
  - ✅ Backend running on EC2 (https://api.noesis.is/health returns 200)                                                                                        
  - ✅ All 4 containers healthy (backend, celery-worker, redis, grobid)                                                                                         
  - ✅ Document upload works end-to-end                                                                                                                         
  - ✅ Draft upload and analysis works                                                                                                                          
  - ✅ BibTeX export functions correctly                                                                                                                        
  - ✅ Toast notifications appear                                                                                                                               
  - ✅ UI styling updates visible (colored icons, solid badges)                                                                                                 
  - ✅ No errors in container logs                                                                                                                              
  - ✅ Memory usage within limits                                                                                                                               
                                                                                                                                                                
  **User Experience Validated:**                                                                                                                                
  - ✅ Login/signup flow works                                                                                                                                  
  - ✅ Can create projects                                                                                                                                      
  - ✅ Can upload documents                                                                                                                                     
  - ✅ Can upload drafts                                                                                                                                        
  - ✅ Can view analysis results                                                                                                                                
  - ✅ Can export BibTeX                                                                                                                                        
  - ✅ UI looks professional (no neon colors, proper styling)                                                                                                   
                                                                                                                                                                
  ---                                                                                                                                                           
                                                                                                                                                                
  ## Estimated Timeline                                                                                                                                         
                                                                                                                                                                
  **Total Time: 40-60 minutes**                                                                                                                                 
                                                                                                                                                                
  - Phase 1 (Git): 10-15 min                                                                                                                                    
  - Phase 2 (Frontend): 5-10 min                                                                                                                                
  - Phase 3 (Backend): 15-20 min                                                                                                                                
  - Phase 4 (Testing): 10-15 min                                                                                                                                
  - Phase 5 (Monitoring): Ongoing                                                                                                                               
                                                                                                                                                                
  **Recommended Time:** Friday evening or Saturday morning (low traffic)                                                                                        
                                                                                                                                                                
  ---                                                                                                                                                           
                                                                                                                                                                
  ## Emergency Contacts & Resources                                                                                                                             
                                                                                                                                                                
  **AWS Console:** https://console.aws.amazon.com/ec2                                                                                                           
  **Vercel Dashboard:** https://vercel.com/dashboard                                                                                                            
  **Supabase Dashboard:** https://supabase.com/dashboard                                                                                                        
                                                                                                                                                                
  **EC2 Instance Details:**                                                                                                                                     
  - Type: t4g.micro (ARM64)                                                                                                                                     
  - Memory: 2GB RAM + 2GB swap                                                                                                                                  
  - Storage: 30GB gp3                                                                                                                                           
  - Region: (check AWS console)                                                                                                                                 
                                                                                                                                                                
  **Important URLs:**                                                                                                                                           
  - Frontend: https://noesis.is                                                                                                                                 
  - API: https://api.noesis.is                                                                                                                                  
  - API Docs: https://api.noesis.is/docs                                                                                                                        
                                                                                                                                                                
  ---                                                                                                                                                           
                                                                                                                                                                
  ## Notes                                                                                                                                                      
                                                                                                                                                                
  - **No database migrations needed** - All changes are application-level                                                                                       
  - **No environment variable changes needed** - Existing .env files are correct                                                                                
  - **Docker Compose handles new containers** - Redis and Celery will start automatically                                                                       
  - **Vercel auto-deploys** - Push to git triggers deployment                                                                                                   
  - **SSL certificates auto-renew** - Let's Encrypt configured                                                                                                  
  - **Cost remains ~$10/month** - New containers within resource limits                                                                                         
                                                                                                                                                                
  **First deployment was successful** - This is an update deployment, lower risk than initial setup.  