import json
import re

import streamlit as st
from google import genai
from google.genai import types
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client as TwilioClient

from prompts import SYSTEM_PROMPT, SUMMARY_REQUEST_PROMPT, WELCOME_MESSAGE_TEMPLATE

GEMINI_MODEL = "gemini-3.8-flash"

st.set_page_config(page_title="MacroSnap", page_icon="🥗")


@st.cache_resource
def get_gemini_client() -> genai.Client:
    return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])


client = get_gemini_client()


def clean_whatsapp_text(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_~`#]", "", text)
    return " ".join(text.split())


def send_whatsapp(user_name: str, whatsapp_number: str, summary: str):
    required_secrets = (
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_WHATSAPP_FROM",
        "TWILIO_CONTENT_SID",
    )
    missing_secrets = [
        secret_name
        for secret_name in required_secrets
        if not st.secrets.get(secret_name)
    ]
    if missing_secrets:
        raise ValueError("Missing Twilio settings: " + ", ".join(missing_secrets))

    recipient_number = whatsapp_number.strip()
    if recipient_number.startswith("whatsapp:"):
        recipient_number = recipient_number.removeprefix("whatsapp:")
    recipient_number = "".join(
        character
        for character in recipient_number
        if character.isdigit() or character == "+"
    )
    if not recipient_number.startswith("+"):
        raise ValueError("Use a WhatsApp number in international format, including +.")

    sender = st.secrets["TWILIO_WHATSAPP_FROM"].strip()
    if not sender.startswith("whatsapp:"):
        sender = f"whatsapp:{sender}"

    twilio_client = TwilioClient(
        st.secrets["TWILIO_ACCOUNT_SID"],
        st.secrets["TWILIO_AUTH_TOKEN"],
    )
    return twilio_client.messages.create(
        from_=sender,
        to=f"whatsapp:{recipient_number}",
        content_sid=st.secrets["TWILIO_CONTENT_SID"],
        content_variables=json.dumps(
            {
                "1": user_name,
                "2": clean_whatsapp_text(summary),
            }
        ),
    )


def generate_conversation_summary() -> str:
    summary_chat = client.chats.create(
        model=GEMINI_MODEL,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
        ),
        history=st.session_state["gemini_chat"].get_history(),
    )
    response = summary_chat.send_message(SUMMARY_REQUEST_PROMPT)
    if not response.text:
        raise ValueError("Gemini returned an empty summary.")
    return response.text


if "messages" not in st.session_state:
    st.session_state["messages"] = []

has_conversation = any(
    message["role"] == "user"
    and (message.get("content") or message.get("image"))
    for message in st.session_state["messages"]
) and any(message["role"] == "assistant" for message in st.session_state["messages"])

title_column, action_column = st.columns([3, 1])
with title_column:
    st.title("MacroSnap")
with action_column:
    send_summary_clicked = st.button(
        "📤 Send to WhatsApp",
        disabled=not has_conversation,
        key="send_whatsapp_summary",
        use_container_width=True,
    )

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
    if send_summary_clicked:
        try:
            summary = st.session_state.get("conversation_summary")
            if not summary:
                summary = generate_conversation_summary()
                st.session_state["conversation_summary"] = summary

            send_whatsapp(
                st.session_state["user_name"],
                st.session_state["whatsapp_number"],
                summary,
            )
        except TwilioRestException as error:
            st.error(
                "Twilio could not send the summary "
                f"(error {error.code}). Check the approved template "
                "and that the recipient has joined your WhatsApp Sandbox."
            )
        except Exception as error:
            st.error(
                "Could not send the WhatsApp summary. Check the Twilio settings "
                f"and try again ({type(error).__name__})."
            )
        else:
            st.session_state["whatsapp_summary_sent_for"] = summary
            st.success("Conversation summary sent to WhatsApp.")

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

    summary_container = st.container()
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
            st.session_state.pop("conversation_summary", None)
            st.session_state.pop("whatsapp_summary_sent_for", None)
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
                    st.rerun()

                    with st.chat_message(assistant_message["role"]):
                        st.markdown(assistant_message["content"])
                else:
                    st.error("Gemini returned an empty response. Please try again.")

    with summary_container:
        if st.session_state["messages"] and st.button(
            "Generate WhatsApp summary",
            key="generate_summary",
        ):
            st.session_state.pop("conversation_summary", None)
            st.session_state.pop("whatsapp_summary_sent_for", None)
            try:
                summary_text = generate_conversation_summary()
            except Exception as error:
                st.error(f"Summary request failed: {error}")
            else:
                if summary_text:
                    st.session_state["conversation_summary"] = summary_text
                else:
                    st.error("Gemini returned an empty summary. Please try again.")

        if st.session_state.get("conversation_summary"):
            summary = st.session_state["conversation_summary"]
            st.subheader("WhatsApp-ready summary")
            st.text(summary)

            if st.session_state.get("whatsapp_summary_sent_for") == summary:
                st.success("Conversation summary sent to WhatsApp.")