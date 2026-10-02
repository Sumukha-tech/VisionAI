import json
from google import genai
from google.genai import types
from prompt import (
    FOOD_ANALYSIS_PROMPT,
    NUTRITION_FIELDS,
    NUTRITION_METRICS,
    SUMMARY_REQUEST_PROMPT,
    SYSTEM_PROMPT,
    WHATS_APP_PROMPT,
    WELCOME_PROMPT,
)
from twilio.rest import Client as twilioClient

import streamlit as st  
GEMINI_API_KEY=st.secrets["GEMINI_API_KEY"]
TWLIO_ACCOUNT_SID=st.secrets["TWLIO_ACCOUNT_SID"]
TWLIO_AUTH_TOKEN=st.secrets["TWLIO_AUTH_TOKEN"]
TWLIO_NUMBER=st.secrets["TWLIO_NUMBER"]
TWLIO_CONTENT_SID=st.secrets["TWLIO_CONTENT_SID"]




@st.cache_resource
def gemini_ai_clients():
    return genai.Client(api_key=GEMINI_API_KEY)
    
    
    
@st.cache_resource
def get_twilio_client():
    return twilioClient(TWLIO_ACCOUNT_SID,TWLIO_AUTH_TOKEN)

gen_ai_clients=gemini_ai_clients()
twilio_client=get_twilio_client()

MODEL_NAME="gemini-2.5-flash"

FOOD_RESPONSE_SCHEMA=types.Schema(
    type=types.Type.OBJECT,
    properties={
        "dish_name":types.Schema(type=types.Type.STRING,description="Name of the dish in the image"),
        "ingredients":types.Schema(type=types.Type.ARRAY,items=types.Schema(type=types.Type.STRING)),
        "portion_size":types.Schema(type=types.Type.STRING,description="Estimated portion size served"),
        "calories":types.Schema(type=types.Type.NUMBER,description="Estimated kcal for the portion"),
        "protein_g":types.Schema(type=types.Type.NUMBER),
        "carbs_g":types.Schema(type=types.Type.NUMBER),
        "fat_g":types.Schema(type=types.Type.NUMBER),
        "healthier_alternative":types.Schema(type=types.Type.STRING),
        "confidence":types.Schema(type=types.Type.STRING,enum=["high","medium","low"]),
        "note":types.Schema(type=types.Type.STRING,description="Uncertainty or extra context"),
    },
    required=["dish_name","ingredients","calories","protein_g","carbs_g","fat_g"],
)

def format_field_value(value):
    if isinstance(value,list):
        return ", ".join(str(item) for item in value)
    if isinstance(value,float) and value.is_integer():
        return int(value)
    return value

def clean_whats_app(text):
    if not text:
        return "No nutrition Summary available"
    text=" ".join(text.split())
    return text[:1500]+"..." if len(text)>1500 else text
    
    
def send_whats_app(to_number,user_name,summary):
    try:
        content_variables=json.dumps(
            {"1":user_name,"2":clean_whats_app(summary)},ensure_ascii=False)
        
        message=twilio_client.messages.create(
            from_=TWLIO_NUMBER,
            to=f"whatsapp:{to_number}",
            content_sid=TWLIO_CONTENT_SID,
            content_variables=content_variables,
        )
        return True,message.sid
    except Exception as e:
        return False,str(e)
        



def build_summary(data,name):
    lines=[f"{name}'s nutrition snapshot"]
    for label,key in NUTRITION_METRICS:
        value=format_field_value(data.get(key))
        if value is None:
            continue
        unit="" if key=="calories" else "g"
        lines.append(f"{label.replace(' (g)','')}: {value}{unit}")
    for label,key in NUTRITION_FIELDS:
        value=format_field_value(data.get(key))
        if value in (None,""):
            continue
        lines.append(f"{label}: {value}")
    return "\n".join(lines)

def render_nutrition_cards(data):
    metric_cols=st.columns(len(NUTRITION_METRICS))
    for col,(label,key) in zip(metric_cols,NUTRITION_METRICS):
        value=format_field_value(data.get(key))
        col.metric(label,"n/a" if value is None else str(value))

    rows=[]
    for label,key in NUTRITION_FIELDS:
        value=format_field_value(data.get(key))
        if value in (None,"",[]):
            continue
        rows.append({"Field":label,"Value":value})

    if rows:
        st.dataframe(rows,hide_index=True,width="stretch")

def render_message(message):
    with st.chat_message(message["role"]):
        if message["kind"]=="text":
            st.markdown(message["content"])
        elif message["kind"]=="image":
            st.image(message["content"])
        elif message["kind"]=="nutrition":
            render_nutrition_cards(message["content"])
    
    
def add_message(role,kind,content):
    st.session_state.messages.append({"role":role,"kind":kind,"content":content})
    render_message(st.session_state.messages[-1])
    
def ask_gemini(parts):
    try:
        return st.session_state.chat.send_message(parts).text or ""
    except Exception as e:
        st.error(f"Error: {e}")
        return "Sorry, I couldn't process your request. Please try again later."
    
def analyze_food(parts):
    try:
        response=gen_ai_clients.models.generate_content(
            model=MODEL_NAME,
            contents=parts,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=FOOD_RESPONSE_SCHEMA,
            ),
        )
        data=json.loads(response.text)
        return True,data
    except Exception as e:
        return False,str(e)
    
    
    
    
    
    #step 1: onboarding section(name, what'sapp number )
if 'onboarding' not in st.session_state:
    st.title("Vision Chat")
    st.caption("Welcome to Vision Chat! snap it,upload it, and let the AI do the rest.")
    
    with st.form("onboardingForm"):
        name = st.text_input("Enter your name")
        whatsapp_number = st.text_input("whatsapp number (with countryCode)",
        placeholder="91+xxxxxxxxxx",
        help="This is the number where macrosnap will text the content ")
        
        
        submitted=st.form_submit_button("Let's goo...")
        
        if submitted:
            if not name.strip() or not whatsapp_number.strip():
                st.warning("Please fill name, whatsapp number")
            
            else:
                st.session_state.name=name.strip()
                st.session_state.whatsapp_number=whatsapp_number.strip()
                
                #activate the ai
                st.session_state.chat=gen_ai_clients.chats.create(
                    model=MODEL_NAME,
                    config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT,temperature=0.2,max_output_tokens=1024)
                )
                st.session_state.messages=[]
                st.session_state.nutrition=None
                st.session_state.onboarding=True
                st.rerun()
    st.stop()    
    
    
##create chat interface

header_col,button_col=st.columns([5,2],vertical_alignment="center")

with header_col:
    st.title("Vision Chat")
    
with button_col:
    send_disabled=len(st.session_state.messages)<=1
    if st.button("Send to whats app",disabled=send_disabled,width="stretch"):
        nutrition=st.session_state.get("nutrition")
        if nutrition:
            summary=build_summary(nutrition,st.session_state.name)
        else:
            with st.spinner("Building summary....."):
                summary=ask_gemini([types.Part.from_text(text=SUMMARY_REQUEST_PROMPT)])
        success,info=send_whats_app(st.session_state.whatsapp_number,st.session_state.name,summary)
        if success:
            st.success("Sent check Your WhatsApp")
        else:
            st.error(f"Failed to send message: {info}")
            
    
st.caption(f"Logged in as {st.session_state.name} updates goes to {st.session_state.whatsapp_number}")

if not st.session_state.messages:
    st.session_state.messages.append(
        {"role":"assistant","kind":"text","content":WELCOME_PROMPT.format(name=st.session_state.name)}
    )

for message in st.session_state.messages:
    render_message(message)
        
user_input=st.chat_input(
    "Ask me anything about the image you uploaded, or upload a new image to get started!",
    accept_file=True,
    file_type=[".jpg",".jpeg",".png"],
)

if user_input:
    photo=user_input.files[0] if user_input.files else None
    text=user_input.text
    parts=[]
    
    if photo is not None:
        photo_bytes=photo.getvalue()
        add_message("user","image",photo_bytes)
        parts.append(types.Part.from_bytes(data=photo_bytes,mime_type=photo.type))
        
    if text:
        add_message("user","text",text)
        parts.append(types.Part.from_text(text=text))
    elif photo is not None:
        parts.append(types.Part.from_text(text=FOOD_ANALYSIS_PROMPT))

    if photo is not None:
        with st.spinner("Crunching the numbers..."):
            ok,nutrition=analyze_food(parts)
        if ok:
            st.session_state.nutrition=nutrition
            add_message("assistant","nutrition",nutrition)
        else:
            st.error(f"Error: {nutrition}")
    else:
        with st.spinner("Crunching the numbers..."):
            answer=ask_gemini(parts)
        add_message("assistant","text",answer)
    
        
    