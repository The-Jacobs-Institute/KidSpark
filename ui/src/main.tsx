import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, useNavigate, useParams, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { BookOpen, Upload, ArrowRight, Plus, Check, Circle, MessageSquare, Shapes, Layers3, ListChecks, Files, Send, LoaderCircle, AlertCircle, Download, Coffee, Square, RotateCcw } from 'lucide-react';
import Markdown from 'react-markdown';
import { request, type Lesson, type Job } from './api';
import './styles.css';

const steps = [
  {name:'Your story', phase:'story_upload', icon:BookOpen},
  {name:'Plan together', phase:'lesson_planning', icon:MessageSquare},
  {name:'Model preview', phase:'model_preview', icon:Shapes},
  {name:'Build review', phase:'segments_connectors', icon:Layers3},
  {name:'Instructions', phase:'build_plan', icon:ListChecks},
  {name:'Lesson bundle', phase:'lesson_bundle', icon:Files},
];
const client = new QueryClient({defaultOptions:{queries:{retry:1,refetchOnWindowFocus:false},mutations:{retry:false}}});

function App() {
  const {id} = useParams();
  const navigate = useNavigate();
  const cache = useQueryClient();
  const lesson = useQuery({queryKey:['lesson',id],queryFn:()=>request<Lesson>(`/sessions/${id}`),enabled:!!id});
  const create = useMutation({mutationFn:()=>request<Lesson>('/sessions',{}),onSuccess:value=>{cache.setQueryData(['lesson',value.session_id],value);navigate(`/lessons/${value.session_id}`)}});
  const state = lesson.data;
  const health=useQuery({queryKey:['health'],queryFn:()=>request<{validation_mode:string}>('/health')});
  const current = state?.phase === 'complete' ? 5 : Math.max(0,steps.findIndex(s=>s.phase === state?.phase));
  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="/"><span className="brand-symbol"><Shapes size={24}/></span><span>KidSpark<small>LESSON STUDIO</small></span></a>
      <button className="new-lesson" onClick={()=>create.mutate()} disabled={create.isPending}><Plus size={18}/> New lesson</button>
      <div className="sidebar-label">YOUR WORKSPACE</div>
      <nav aria-label="Lesson progress"><ol>{steps.map((step,i)=><li key={step.phase} className={i===current?'current':i<current?'finished':''}><span className="step-icon">{i<current?<Check size={18}/>:<step.icon size={18}/>}</span><span>{step.name}</span>{i===current&&<span className="active-dot"/>}</li>)}</ol></nav>
      <div className="sidebar-foot"><BookOpen size={16}/><span>Story. Discovery. Invention.</span><small>The Jacobs Institute</small></div>
    </aside>
    <div className="workspace">
      <header><span>Teacher workspace <span className="divider">/</span> {steps[current].name}</span><span className="save-state"><Circle size={7} fill="currentColor"/> {state?'Lesson saved':'New lesson'}</span></header>
      <main>
        {health.data?.validation_mode==='fixtures'&&<Notice text="Local UI validation fixtures. No live AI calls or physically validated classroom instructions."/>}
        {(lesson.error||create.error)&&<Notice text={(lesson.error||create.error)?.message||'Unable to load lesson'}/>}
        {lesson.isLoading?<div className="loading"><LoaderCircle className="spin"/> Opening your lesson</div>:<>
          <div className="page-heading"><div className="eyebrow">STEP {String(current+1).padStart(2,'0')} OF 06</div><h1>{state?.storybook_analysis?.title && current>0 ? state.storybook_analysis.title : 'Every lesson starts with a story.'}</h1><p>{['Choose the story you want to bring into your classroom.','Shape a lesson around your students, your story, and a little invention.','Review the design before turning it into a classroom build.','Check how the model comes together with your available kit.','Review the build sequence before preparing your classroom materials.','Your teaching materials, together in one place.'][current]}</p></div>
          {current===0?<StoryUpload id={id} initialText={state?.storybook_text} onCreate={async()=>{const value=await create.mutateAsync();return value.session_id}}/>:state&&current===1?<Planning lesson={state}/>:state&&<BuildStage lesson={state} index={current}/>}
        </>}
      </main>
      <footer>KidSpark <span>Created for thoughtful, hands-on learning.</span></footer>
    </div>
  </div>;
}

function Notice({text}:{text:string}) {return <div className="notice" role="alert"><AlertCircle size={19}/><span>{text}</span></div>}

function StoryUpload({id,onCreate,initialText}:{id?:string;initialText?:string;onCreate:()=>Promise<string>}) {
  const [mode,setMode]=useState<'text'|'file'>('text');
  const [text,setText]=useState(initialText||'');
  const [file,setFile]=useState<File>();
  const cache=useQueryClient();
  const upload=useMutation({mutationFn:async()=>{
    const sid=id||await onCreate();
    const form=new FormData();
    if(mode==='file'&&file)form.set('file',file);else form.set('text',text);
    const result=await request<Lesson>(`/sessions/${sid}/upload`,form);
    cache.setQueryData(['lesson',sid],result);return result;
  }});
  return <div className="story-layout"><section className="story-input">
    <div className="section-title"><BookOpen size={22}/><h2>Add your story</h2></div>
    <div className="tabs" role="tablist"><button role="tab" aria-selected={mode==='text'} className={mode==='text'?'selected':''} onClick={()=>setMode('text')}>Paste or write</button><button role="tab" aria-selected={mode==='file'} className={mode==='file'?'selected':''} onClick={()=>setMode('file')}>Upload a file</button></div>
    {mode==='text'?<><label htmlFor="story">Story text</label><textarea id="story" className="story-text" value={text} onChange={e=>setText(e.target.value)} placeholder="Add the title and story here..." maxLength={100000}/><div className="input-meta"><span>Your story stays with this lesson.</span><span>{text.length.toLocaleString()} characters</span></div></>:<label className="file-drop"><Upload size={32}/><strong>{file?.name||'Choose your story file'}</strong><span>PDF, TXT, or Markdown · Up to 20 MB</span><input aria-label="Story file" type="file" accept=".pdf,.txt,.md" onChange={e=>setFile(e.target.files?.[0])}/></label>}
    {upload.error&&<Notice text={upload.error.message}/>}
    <div className="action-row"><span>Next: discover themes and lesson ideas</span><button className="primary" disabled={upload.isPending||(mode==='text'?!text.trim():!file)} onClick={()=>upload.mutate()}>{upload.isPending?<><LoaderCircle className="spin" size={18}/> Reading your story</>:<>Explore this story <ArrowRight size={18}/></>}</button></div>
  </section><aside className="story-aside"><span className="section-tag">A LITTLE INSPIRATION</span><h2>What will your students discover?</h2><p>A character solving a problem. A structure that needs to stand. An idea waiting to be built.</p><hr/><h3>One story, a complete lesson</h3><ul><li><Check size={16}/> Learning goals for your classroom</li><li><Check size={16}/> A model to build and explore</li><li><Check size={16}/> Teaching materials to take with you</li></ul><div className="teacher-note"><BookOpen size={24}/><p>Start with a story your students love. The lesson takes shape together.</p></div></aside></div>;
}

function Planning({lesson}:{lesson:Lesson}) {
  const [message,setMessage]=useState('');
  const cache=useQueryClient();
  const send=useMutation({mutationFn:()=>request<Lesson>(`/sessions/${lesson.session_id}/message`,{message}),onSuccess:value=>{cache.setQueryData(['lesson',lesson.session_id],value);setMessage('')}});
  const confirm=useMutation({mutationFn:()=>request<Lesson>(`/sessions/${lesson.session_id}/confirm-planning`,{}),onSuccess:value=>cache.setQueryData(['lesson',lesson.session_id],value)});
  const labels:Record<string,string>={target_grade:'Grade',duration_minutes:'Lesson length',core_concept:'Central idea',build_object:'Build idea',learning_goals:'Learning goals',moving_parts:'Moving parts',static_parts:'Fixed parts',literacy_focus:'Literacy',sel_focus:'Social-emotional focus',constraints:'Classroom considerations'};
  const detail=(key:string)=>key==='moving_parts'&&lesson.planning_state.movement_confirmed&&!describe(lesson.planning_state[key])?'Fully static':describe(lesson.planning_state[key]);
  return <div className="planning-layout"><section className="conversation"><div className="section-title"><MessageSquare size={21}/><h2>Plan with KidSpark</h2></div>
    <div className="messages">{!lesson.teacher_messages.length&&<div className="assistant-message"><span className="speaker">KIDSPARK</span><p>Let’s explore <strong>{lesson.storybook_analysis?.title}</strong>. What grade are you teaching, and how much time do you have?</p><p>Some ideas from your story: {lesson.storybook_analysis?.buildable_objects?.join(', ')}.</p></div>}
    {lesson.teacher_messages.map((m,i)=><div key={i} className={m.role==='user'?'teacher-message':'assistant-message'}><span className="speaker">{m.role==='user'?'YOU':'KIDSPARK'}</span><Markdown>{m.content}</Markdown></div>)}{send.isPending&&<div className="thinking"><LoaderCircle size={16} className="spin"/> Thinking about your lesson</div>}</div>
    {send.error&&<Notice text={send.error.message}/>}<form className="composer" onSubmit={e=>{e.preventDefault();if(message.trim())send.mutate()}}><textarea aria-label="Message to planning coach" value={message} onChange={e=>setMessage(e.target.value)} placeholder="Tell me about your classroom..." maxLength={8000}/><button className="icon-button primary" aria-label="Send message" title="Send message" disabled={send.isPending||!message.trim()}><Send size={19}/></button></form>
    <small className="evidence-state">{lesson.rag_status==='ok'?'Using curriculum references':'Curriculum references are not currently available. Review suggested alignment.'}</small>
  </section><aside className="lesson-details"><h2>Lesson at a glance</h2><dl>{Object.entries(labels).map(([key,label])=><React.Fragment key={key}><dt>{label}</dt><dd>{detail(key)||<span className="muted">Not decided yet</span>}</dd></React.Fragment>)}</dl>{confirm.error&&<Notice text={confirm.error.message}/>}<button className="primary wide" disabled={!lesson.planning_state.required_complete||confirm.isPending} onClick={()=>confirm.mutate()}>Confirm lesson <ArrowRight size={18}/></button></aside></div>;
}

function describe(value:unknown):string {
  if(value==null)return '';
  if(Array.isArray(value))return value.map(v=>typeof v==='object'&&v?String(v.part_name||v.label||''):String(v)).join(', ');
  return typeof value==='object'?'':String(value);
}

function BuildStage({lesson,index}:{lesson:Lesson;index:number}) {
  const cache=useQueryClient();
  const [refinement,setRefinement]=useState('');
  const [blocks,setBlocks]=useState<number>();
  const [regions,setRegions]=useState<number>();
  const [documentNotes,setDocumentNotes]=useState('');
  const [connectionNotes,setConnectionNotes]=useState<string|undefined>(undefined);
  const stage=index===2?'model-preview':index===5?'documents':'segments';
  const hasJob=stage==='model-preview'?lesson.model_preview_job_id:stage==='documents'?lesson.document_job_id:lesson.segment_job_id;
  const job=useQuery({queryKey:['job',lesson.session_id,stage,hasJob],queryFn:()=>request<Job>(`/sessions/${lesson.session_id}/${stage}`),enabled:!!hasJob,refetchInterval:q=>['queued','running'].includes(q.state.data?.status||'queued')?2500:false});
  const action=useMutation({mutationFn:(name:string)=>request(`/sessions/${lesson.session_id}/${name}`,{}),onSuccess:()=>cache.invalidateQueries({queryKey:['lesson',lesson.session_id]})});
  const control=useMutation({mutationFn:(name:'cancel'|'resume')=>request(`/sessions/${lesson.session_id}/jobs/${hasJob}/${name}`,{}),onSuccess:()=>cache.invalidateQueries({queryKey:['job',lesson.session_id]})});
  const editDocuments=useMutation({mutationFn:()=>request(`/sessions/${lesson.session_id}/documents/refine`,{notes:documentNotes}),onSuccess:()=>{setDocumentNotes('');cache.invalidateQueries({queryKey:['lesson',lesson.session_id]})}});
  const reviewConnections=useMutation({mutationFn:()=>request<Lesson>(`/sessions/${lesson.session_id}/connectors/review`,{notes:(connectionNotes??lesson.connector_review?.notes)?.trim()||'Teacher reviewed the intended moving parts and connections.'}),onSuccess:value=>cache.setQueryData(['lesson',lesson.session_id],value)});
  const revise=useMutation({mutationFn:()=>request(`/sessions/${lesson.session_id}/model-preview/refine`,{refinement,max_validated_blocks:effectiveBlocks,max_semantic_segments:effectiveRegions}),onSuccess:()=>cache.invalidateQueries({queryKey:['lesson',lesson.session_id]})});
  const running=['queued','running'].includes(job.data?.status||'');
  const results=job.data?.result||{};
  const constraints=(results.context as {build_constraints?:Record<string,number>}|undefined)?.build_constraints;
  const effectiveBlocks=blocks??lesson.build_constraints?.max_validated_blocks??constraints?.max_validated_blocks??28;
  const effectiveRegions=regions??lesson.build_constraints?.max_semantic_segments??constraints?.max_semantic_segments??4;
  const plan=(results.build_plan||{}) as Record<string,unknown>;
  const validation=(plan.validated_planner||{}) as Record<string,unknown>;
  const valid=validation.final_claim_valid===true;
  const images=findArtifacts(results,/\.(png|jpg|jpeg|webp)$/i);
  const pdfs=findArtifacts(results,/\.pdf$/i);
  const instructionSteps=Array.isArray(validation.instruction_steps)?validation.instruction_steps:[];
  const fixture=validation.build_status==='FIXTURE_ONLY';
  const notebook=(plan.notebook_outputs||{}) as Record<string,unknown>;
  const connections=Array.isArray(notebook.connector_candidates)?notebook.connector_candidates:[];
  const reviewRequired=(plan.validation as {connector_review_required?:boolean}|undefined)?.connector_review_required===true;
  const reviewed=lesson.connector_review?.job_id===lesson.segment_job_id;
  const confirm=index===2?'confirm-model':index===3?'confirm-segments':index===4?'confirm-build-plan':'confirm-documents';
  return <section className="build-stage">
    {(action.error||job.error||control.error)&&<Notice text={(action.error||job.error||control.error)?.message||''}/>}
    {!hasJob&&<div className="build-start"><Shapes size={44}/><h2>{index===2?'Bring your lesson idea to life':index===5?'Prepare your teaching materials':'Turn the model into a build'}</h2><p>{index===2?`Create a model of ${describe(lesson.planning_state.build_object)||'your chosen object'}.`:'KidSpark will check the next stage before presenting the result.'}</p><button className="primary" disabled={action.isPending} onClick={()=>action.mutate(stage)}> {action.isPending?<LoaderCircle size={18} className="spin"/>:<ArrowRight size={18}/>} {index===2?'Generate model':index===5?'Create lesson bundle':'Generate build plan'}</button></div>}
    {running&&<div className="progress-area" aria-live="polite"><Coffee className="steam" size={36}/><div><h2>{job.data?.stage}</h2><p>{job.data?.message}</p><progress max={100} value={job.data?.progress}/><small>Your lesson is saved. You can return to this page.</small></div></div>}
    {running&&<button disabled={control.isPending} onClick={()=>control.mutate('cancel')}><Square size={16}/> Stop processing</button>}
    {['error','cancelled'].includes(job.data?.status||'')&&<><Notice text={job.data?.message||'Processing stopped'}/>{job.data?.retryable?<button className="primary" disabled={control.isPending} onClick={()=>control.mutate('resume')}><RotateCcw size={16}/> Resume saved progress</button>:<p className="muted">Please contact the project team to check the saved job before generating again.</p>}</>}
    {index<5&&!running&&<details className="refinement"><summary>Adjust the model and build limits</summary><label htmlFor="revision">What should change?</label><textarea id="revision" value={refinement} onChange={e=>setRefinement(e.target.value)} placeholder="Keep the essential parts, simplify the shape..."/><div className="constraint-fields"><label>Maximum pieces<input type="number" min={8} max={64} value={effectiveBlocks} onChange={e=>setBlocks(Number(e.target.value))}/></label><label>Maximum regions<input type="number" min={1} max={8} value={effectiveRegions} onChange={e=>setRegions(Number(e.target.value))}/></label></div>{revise.error&&<Notice text={revise.error.message}/>}<button className="primary" disabled={!refinement.trim()||revise.isPending||effectiveBlocks<8||effectiveBlocks>64||effectiveRegions<1||effectiveRegions>8} onClick={()=>revise.mutate()}>Revise model <ArrowRight size={18}/></button></details>}
    {job.data?.status==='complete'&&<><div className="result-heading"><h2>{index===2?'Your model preview':index===5?'Classroom materials':index===4?'Build instructions':'Build assessment'}</h2>{index!==2&&index!==5&&<span className={valid&&!fixture?'status-good':'status-warning'}>{fixture?'Test fixture only':valid?'Validated':'Needs revision'}</span>}</div>
      {images.length>0?<div className="image-grid">{images.slice(0,12).map(a=><figure key={a.path}><img src={artifactURL(lesson.session_id,a.path)} alt={a.label.replaceAll('_',' ')}/><figcaption>{a.label.replaceAll('_',' ')}</figcaption></figure>)}</div>:index!==5&&<p className="muted">No review images are available for this result.</p>}
      {index===4&&valid&&<ol className="instruction-list">{instructionSteps.map((step,i)=><li key={i}><h3>{String(step.title||`Step ${i+1}`)}</h3><p>{String(step.teacher_instruction||step.student_instruction||'')}</p>{step.image_path&&<img src={artifactURL(lesson.session_id,String(step.image_path))} alt={`Build step ${i+1}`}/>}</li>)}</ol>}
      {index===4&&valid&&!instructionSteps.length&&<Notice text="The instruction sequence is missing. This build cannot be approved yet."/>}
      {index!==2&&index!==5&&!valid&&<Notice text={String(validation.reason||'This model has not passed the build checks. Do not use it as classroom instructions.')}/>}
      {index===3&&(connections.length>0||reviewRequired)&&<section className="connection-review"><h2>Moving parts and connections</h2><ul>{connections.map((item,i)=><li key={i}><strong>{String(item.part_name||`Connection ${i+1}`)}</strong>: {String(item.movement||item.connector_type||item.status||'Review required')}</li>)}</ul><label htmlFor="connection-notes">Classroom connection notes</label><textarea id="connection-notes" value={connectionNotes??lesson.connector_review?.notes??''} onChange={e=>setConnectionNotes(e.target.value)}/>{reviewConnections.error&&<Notice text={reviewConnections.error.message}/>}<button className="primary" disabled={reviewConnections.isPending} onClick={()=>reviewConnections.mutate()}><Check size={16}/>{reviewed?'Update connection review':'Confirm connection review'}</button></section>}
      {pdfs.map(a=><a className="download-row" key={a.path} href={artifactURL(lesson.session_id,a.path)} target="_blank" rel="noreferrer"><Files size={22}/><span>{a.path.split(/[\\/]/).pop()?.replace(/\.pdf$/i,'').replaceAll('_',' ')}</span><Download size={19}/></a>)}
      {index===5&&<details className="refinement"><summary>Revise classroom materials</summary><label htmlFor="document-notes">What should change in the lesson plan, activity guide, or slides?</label><textarea id="document-notes" value={documentNotes} maxLength={3000} onChange={e=>setDocumentNotes(e.target.value)}/>{editDocuments.error&&<Notice text={editDocuments.error.message}/>}<button className="primary" disabled={!documentNotes.trim()||editDocuments.isPending} onClick={()=>editDocuments.mutate()}><RotateCcw size={16}/> Revise materials</button></details>}
      <div className="action-row"><span>{lesson.phase==='complete'?'Your materials are saved and available above.':'Review the result before continuing.'}</span><button className="primary" disabled={action.isPending||([3,4].includes(index)&&!valid)||(index===3&&reviewRequired&&!reviewed)||(index===4&&!instructionSteps.length)||lesson.phase==='complete'} onClick={()=>action.mutate(confirm)}>{lesson.phase==='complete'?'Lesson complete':'Approve and continue'}<ArrowRight size={18}/></button></div>
    </>}
  </section>;
}

function findArtifacts(value:unknown,pattern:RegExp,label=''): {path:string;label:string}[] {
  if(typeof value==='string'&&pattern.test(value))return [{path:value,label}];
  if(value&&typeof value==='object')return Object.entries(value).flatMap(([key,v])=>findArtifacts(v,pattern,key)).filter((item,i,all)=>all.findIndex(a=>a.path===item.path)===i);
  return [];
}
function artifactURL(id:string,path:string){return `/api/v1/sessions/${id}/artifact?path=${encodeURIComponent(path)}`}

createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={client}><BrowserRouter><Routes><Route path="/" element={<App/>}/><Route path="/lessons/:id" element={<App/>}/><Route path="*" element={<App/>}/></Routes></BrowserRouter></QueryClientProvider></React.StrictMode>);
