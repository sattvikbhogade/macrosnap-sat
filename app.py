import streamlit as st
from google import genai
from google.genai import types

from prompts import SYSTEM_PROMPT, WELCOME_MESSAGE_TEMPLATE

GEMINI_MODEL = "gemini-3.8-flash"

st.set_page_config(page_title="MacroSnap", page_icon="🥗")


@st.cache_resource
def get_gemini_client() -> genai.Client:
    return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])


client = get_gemini_client()

if "messages" not in st.session_state:
    st.session_state["messages"] = []

st.title("MacroSnap")
st.caption(f"Gemini model configured: {GEMINI_MODEL}")

if "onboarding_complete" not in st.session_state:
    st.session_state["onboarding_complete"] = False

if not st.session_state["onboarding_complete"]:
    st.subheader("Let's get to know you")

    with st.form("onboarding_form"):
        name = st.text_input("Your name")
        whatsapp_number = st.text_input(
            "WhatsApp number",
            placeholder="+1 555 123 4567",
        )
        submitted = st.form_submit_button("Continue")

    if submitted:
        cleaned_name = name.strip()
        cleaned_whatsapp_number = whatsapp_number.strip()

        if not cleaned_name or not cleaned_whatsapp_number:
            st.error("Enter both your name and WhatsApp number.")
        else:
            st.session_state["user_name"] = cleaned_name
            st.session_state["whatsapp_number"] = cleaned_whatsapp_number
            st.session_state["gemini_chat"] = client.chats.create(
                model=GEMINI_MODEL,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                ),
            )
            st.session_state["onboarding_complete"] = True
            st.rerun()
else:
    st.write(
        WELCOME_MESSAGE_TEMPLATE.format(
            name=st.session_state["user_name"],
        )
    )

    for message in st.session_state["messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Tell me what you ate..."):
        user_message = {
            "role": "user",
            "kind": "text",
            "content": prompt,
        }
        st.session_state["messages"].append(user_message)

        with st.chat_message(user_message["role"]):
            st.markdown(user_message["content"])

        try:
            response = st.session_state["gemini_chat"].send_message(prompt)
            response_text = response.text
        except Exception as error:
            st.error(f"Gemini request failed: {error}")
        else:
            if response_text:
                assistant_message = {
                    "role": "assistant",
                    "kind": "text",
                    "content": response_text,
                }
                st.session_state["messages"].append(assistant_message)

                with st.chat_message(assistant_message["role"]):
                    st.markdown(assistant_message["content"])
            else:
                st.error("Gemini returned an empty response. Please try again.")