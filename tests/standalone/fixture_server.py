"""Explicit local UI test harness. Never included in the deployment image.

Replaces external boundaries, not the API, persistence, approvals, or PDF renderer.
All artifacts are visibly labeled fixtures and are not classroom instructions.
"""
import os
os.environ["KIDSPARK_APP_DATABASE_URL"] = "sqlite:///work/browser-fixtures.sqlite"
os.environ["KIDSPARK_WORKER_MODE"] = "disabled"
os.environ["KIDSPARK_VALIDATION_MODE"] = "fixtures"

from pathlib import Path
from PIL import Image, ImageDraw
from api import main
from agents import orchestrator as workflow
from build3d import jobs, pipeline
from models.schemas import StoryAnalysis, ConsultationResponse, PlanningStateUpdate, ConsultationSummary, BlockRequirements, ArtifactPart
from runtime.worker import execute


async def analysis(text):
    return StoryAnalysis(title=text.splitlines()[0], characters=["Nia", "Sam"], settings=["stream"],
        key_events=["Build, test, and improve a bridge"], themes=["teamwork", "testing ideas"],
        buildable_objects=["bridge"], vocabulary_opportunities=["support", "test", "balance"], sel_angles=["collaboration"])


async def converse(*args, **kwargs):
    return ConsultationResponse(response="Let's build a short bridge with two sturdy supports. Test its balance, improve one part, and explain what changed. I've recorded your classroom choices for review.",
        planning_update=PlanningStateUpdate(target_grade="1st Grade",duration_minutes=40,
        core_concept="Testing and teamwork",learning_goals=["Build and test a stable bridge","Explain a design improvement"],
        build_object="bridge", moving_parts=[], movement_confirmed=True,
        static_parts=[{"part_name":"supports","movement":"static"},{"part_name":"deck","movement":"static"}],
        static_parts_confirmed=True,constraints=["Work in pairs with one standard kit"],
        literacy_focus="Explain support and balance",sel_focus="Listen to a partner's idea"))


async def summary(story_analysis, **kwargs):
    return ConsultationSummary(agreed_theme="Testing and teamwork",agreed_artifact="bridge",
        artifact_parts=["supports","deck"], learning_objectives=["Build a stable bridge","Explain an improvement"],
        grade_band="1st Grade",duration_minutes=40,literacy_focus="Support and balance",sel_focus="Collaboration",
        teacher_preferences=["Pairs"],kb_evidence_used=[],storybook_title=story_analysis.title)


async def requirements(**kwargs):
    return BlockRequirements(artifact_label="bridge",parts=[ArtifactPart(part_name=n,movement="static",
        suggested_pieces=["standard_2x2x2"],piece_count=4,notes="Stable support") for n in ["supports","deck"]],
        connector_types_needed=[],total_cube_blocks=8,total_special_pieces=0,articulation_summary="Fully static")


def picture(directory):
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/'bridge-fixture.png'
    image=Image.new('RGB',(900,550),'white')
    draw=ImageDraw.Draw(image)
    draw.text((25,20),'LOCAL UI TEST FIXTURE - NOT BUILD INSTRUCTIONS',fill='#985923')
    for x,y in [(240,310),(240,250),(600,310),(600,250),(240,190),(330,190),(420,190),(510,190),(600,190)]:
        draw.rectangle((x,y,x+80,y+55),fill='#428fba',outline='#205070',width=3)
    draw.text((260,440),'Two supports and a deck: layout fixture only',fill='#345749')
    image.save(path)
    return str(path)


def preview(context,directory,progress):
    progress('Generating fixture',50,'Preparing a local validation example')
    return {'context':context,'rodin':{'task_uuid':f'fixture-{directory.name}','files':[]},'preview_image':picture(directory)}


def segments(context,task,files,directory,progress):
    return {'context':context,'rodin':{'task_uuid':task,'files':files},'build_plan':{
        'final_build_image':picture(directory),'validated_planner':{'final_claim_valid':True,'build_status':'FIXTURE_ONLY',
        'instruction_steps':[{'step_number':1,'title':'Compare the supports (fixture)',
        'teacher_instruction':'Local UI test only. Compare the supports; this is not validated building guidance.'}]}}}


def documents(story,context,plan,directory,progress):
    from build3d.classroom_pdf import write_classroom_pdf
    directory.mkdir(parents=True,exist_ok=True)
    results={}
    for kind in ['lesson_plan','activity_guide','slide_companion']:
        source=directory/f'{kind}.md'
        source.write_text('# The Little Bridge - LOCAL VALIDATION FIXTURE\n\n## Teacher Overview\nThis document tests local rendering and download behavior. It is not an approved classroom lesson.\n\n## Learning Objectives\n- Describe how supports help a bridge stand.\n- Test one change and explain what happened.\n\n## Step 01 - Read\nDiscuss why the first bridge bent. Ask students to use evidence from the story.\n\n## Step 02 - Learn and Explore\nCompare wide and narrow supports and describe the differences.\n\n## Step 03 - Invent\nThe picture below is a UI layout fixture, not validated construction guidance.\nImage: '+plan['final_build_image']+'\n\n## Reflection\nWhat changed when you tested your idea?\n',encoding='utf-8')
        pdf=write_classroom_pdf(source)
        results[kind]={'pdf_path':str(pdf),'title':kind.replace('_',' ')}
    return {'document_bundle':{'all_valid':True,'documents':results}}


main.provider_configured=lambda:True
workflow.analyze_storybook=analysis
workflow.handle_consultation_message=converse
workflow.finalize_consultation=summary
workflow.finalize_block_requirements=requirements
workflow.retrieve_teacher_evidence=lambda *a,**kw:{'status':'fixture','trace':[]}
pipeline.create_rodin_preview=preview
pipeline.create_segments_and_build_plan=segments
pipeline.create_document_bundle=documents
jobs.dispatch=execute
app=main.app
