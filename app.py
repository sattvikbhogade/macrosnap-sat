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
            if message["kind"] == "image":
                st.image(message["image"], caption=message["file_name"])
            if message["content"]:
                st.markdown(message["content"])

    chat_submission = st.chat_input(
        "Tell me what you ate or attach a meal photo...",
        accept_file=True,
        file_type=["jpg", "jpeg", "png"],
    )
    if chat_submission:
        if isinstance(chat_submission, str):
            prompt = chat_submission.strip()
            uploaded_files = []
        else:
            prompt = chat_submission.text.strip()
            uploaded_files = chat_submission.files

        image_file = uploaded_files[0] if uploaded_files else None
        image_mime_type = None
        image_bytes = None

        if image_file:
            extension = image_file.name.rsplit(".", 1)[-1].lower()
            image_mime_type = {
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "png": "image/png",
            }.get(extension)

            if not image_mime_type:
                st.error("Please upload a JPG, JPEG, or PNG image.")
            else:
                image_bytes = image_file.getvalue()

        if (prompt or image_bytes) and (not image_file or image_mime_type):
            user_message = {
                "role": "user",
                "kind": "image" if image_bytes else "text",
                "content": prompt,
            }
            if image_bytes:
                user_message["image"] = image_bytes
                user_message["mime_type"] = image_mime_type
                user_message["file_name"] = image_file.name

            st.session_state["messages"].append(user_message)

            with st.chat_message(user_message["role"]):
                if image_bytes:
                    st.image(image_bytes, caption=image_file.name)
                if prompt:
                    st.markdown(prompt)

            try:
                if image_bytes:
                    message_parts = []
                    if prompt:
                        message_parts.append(prompt)
                    message_parts.append(
                        types.Part.from_bytes(
                            data=image_bytes,
                            mime_type=image_mime_type,
                        )
                    )
                    response = st.session_state["gemini_chat"].send_message(
                        message_parts,
                    )
                else:
                    response = st.session_state["gemini_chat"].send_message(
                        prompt,
                    )
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