"""
Google Gemini structured-output resume parser.

Uses the google-genai SDK with a Pydantic schema so Gemini returns strict,
validated JSON matching our ParsedResume model.
"""

import json
from typing import Optional

from google import genai
from google.genai import types

from app.core.config import settings
from app.schemas.resume import ParsedResume


class GeminiParser:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is required")
        self.client = genai.Client(api_key=self.api_key)

    async def parse_resume(self, resume_text: str) -> ParsedResume:
        """
        Send resume text to Gemini with structured output and return a
        validated ParsedResume Pydantic instance.
        """
        system_instruction = (
            "You are an expert HR resume parser. Extract and normalize the "
            "candidate's resume into the exact JSON schema provided. "
            "Rules:\n"
            "1. Contact: full_name, email, phone, city, linkedin_url, github_url, portfolio_url.\n"
            "2. Profile: 2–3 sentence simplified summary, total years of experience "
            "(calculate from work history), and primary_domain "
            "(e.g. Software Engineering, Digital Marketing, Operations).\n"
            "3. Work Experience: array of {company, job_title, start_date, end_date ('Present' if current), bullets (2–4 concise items)}.\n"
            "4. Education: array of {degree, institution, graduation_year}.\n"
            "5. Skills: categorize into technical_skills, tools, soft_skills (arrays of strings).\n"
            "6. Additional Info: hobbies_interests, languages, certifications (arrays of strings).\n"
            "7. If a field is not found, use empty string / empty array / null. Never invent data.\n"
            "Return ONLY valid JSON matching the schema."
        )

        # Use the async API to avoid blocking the event loop
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=f"{system_instruction}\n\nRESUME TEXT:\n{resume_text}")],
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ParsedResume,
                temperature=0.1,
            ),
        )

        raw_text = response.text or "{}"
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            # Fallback: try to extract JSON from markdown fences
            start = raw_text.find("{")
            end = raw_text.rfind("}")
            if start != -1 and end != -1:
                data = json.loads(raw_text[start:end + 1])
            else:
                raise ValueError(f"Gemini returned non-JSON: {raw_text[:500]}")

        return ParsedResume(**data)
