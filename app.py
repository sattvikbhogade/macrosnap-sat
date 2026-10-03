import streamlit as st
from google import genai

GEMINI_MODEL = "gemini-3.8-flash"

st.set_page_config(page_title="MacroSnap", page_icon="🥗")


@st.cache_resource
def get_gemini_client() -> genai.Client:
    return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])


client = get_gemini_client()

st.title("MacroSnap")
st.caption(f"Gemini model configured: {GEMINI_MODEL}")