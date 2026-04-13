"""
WISE 計畫 AI 訪談 Agent — FastAPI 後端（Gemini + Google Drive 版）
教育學院非典型就業校友調查
"""

import os
import io
import json
import uuid
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# ── 設定 ──────────────────────────────────────────────────────────────
GEMINI_API_KEY = "AIzaSyCZpKESo8AC-9gqwzGXsdE_Ry-UFkLMsYw"
GEMINI_MODEL   = "gemini-3.1-flash-image-preview"

# Google Drive：從環境變數讀取（Render 上設定）
# GDRIVE_FOLDER_ID  : 目標資料夾的 ID（從 Drive URL 取得）
# GDRIVE_CREDENTIALS: service account JSON 的完整內容（字串）
GDRIVE_FOLDER_ID   = os.environ.get("GDRIVE_FOLDER_ID", "")
GDRIVE_CREDENTIALS = os.environ.get("GDRIVE_CREDENTIALS", "")

# 本地備份（本機跑時也存一份）
TRANSCRIPTS_DIR = Path("/tmp/transcripts")
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

client = genai.Client(api_key=GEMINI_API_KEY)

# ── System Prompt ─────────────────────────────────────────────────────
INTERVIEW_SYSTEM_PROMPT = """你是一位溫暖、專業的學術研究訪談員，代表國立臺灣師範大學教育學院 WISE 研究計畫進行訪談。

【角色設定】
- 你是 AI 訪談員。訪談開始時，你必須清楚告知受訪者「我是 AI 訪談員」，並說明研究目的。
- 語氣：溫暖親切，帶有學術嚴謹性；像一位真正關心對方故事的研究者，而非機械問卷。
- 語言：繁體中文。

【訪談目標】
蒐集教育學院「非典型就業」校友（即目前非從事中小學教師、學校行政、教育公務員等傳統教育職的畢業生）的以下資訊：
1. 教育學院培育的哪些能力對其非典型職涯有實際貢獻
2. 在教育學院「沒有學到」但職場迫切需要的關鍵技能或素養（課程缺口）

【四大訪談主題與時間配置】
主題一：非典型職涯的形成歷程（約 5 分鐘）
- 目前工作內容與職責
- 進入這個職涯領域的歷程
- 選擇非典型職涯的關鍵時刻或原因

主題二：教育學院培育能力的職涯價值（約 8-10 分鐘）——最核心
- 在職場中，哪些能力是你覺得「幸好在教育學院學過」的
- 請給出具體工作情境的例子
- 這些能力讓你有哪些優勢或感受

主題三：課程缺口——「沒學到」的關鍵技能（約 8-10 分鐘）——最核心
- 進入職場後，你遇過哪些「當時學校沒教但非常需要」的技能或知識？
- 請說明是在什麼工作情境下感受到這個缺口
- 你如何自學或補足這些缺口？

主題四：對後輩的建議（約 5 分鐘）
- 對想走非典型職涯的學弟妹說一件事
- 在學期間的遺憾，或希望自己當時有做的事

【追問邏輯】
以下情況需要深挖，不要直接跳到下一個問題：
- 回答過於抽象（例如「對我很有幫助」）→ 追問「能不能舉一個具體的工作情境？」
- 提到有趣但未展開的線索 → 追問「你剛才提到 [X]，可以多說一點嗎？」
- 某主題三層尚未達到：具體情境描述、個人詮釋、情感評價 → 分別追問

【資料飽和判斷】
每個主題達到以下三層才推進：
1. 具體情境：有描述特定的工作事件或場景
2. 個人詮釋：受訪者說明了為什麼重要或有什麼意義
3. 情感評價：受訪者表達了感受或態度

【結束判斷】
滿足以下任一條件時，自然結束訪談：
- 四大主題均已達到資料飽和，且超過 20 分鐘
- 受訪者主動表示時間到或想結束
- 對話已達 30 分鐘

結束時的動作：
1. 感謝受訪者的分享（具體提及 1-2 個印象深刻的內容）
2. 簡短說明資料將匿名用於教育學院課程改革
3. 詢問是否有任何補充
4. 正式道謝，說明訪談結束

【重要限制】
- 不評判受訪者的職涯選擇，保持中立溫暖
- 不主動分享自己的意見或建議，只聆聽與追問
- 若受訪者問到非相關話題，簡短回應後引回訪談

【訪談結束標記】
當你確認訪談正式結束時，在你最後一條回覆末尾加上：
<<INTERVIEW_COMPLETE>>
"""

# ── Google Drive 上傳 ─────────────────────────────────────────────────
def upload_to_drive(filename: str, content: str):
    """將逐字稿上傳到 Google Drive 指定資料夾"""
    if not GDRIVE_FOLDER_ID or not GDRIVE_CREDENTIALS:
        return  # 未設定則跳過

    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload
        from google.oauth2 import service_account

        creds_dict = json.loads(GDRIVE_CREDENTIALS)
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        service = build("drive", "v3", credentials=creds)

        file_metadata = {
            "name": filename,
            "parents": [GDRIVE_FOLDER_ID],
            "mimeType": "text/markdown",
        }
        media = MediaIoBaseUpload(
            io.BytesIO(content.encode("utf-8")),
            mimetype="text/plain",
        )
        service.files().create(
            body=file_metadata, media_body=media, fields="id"
        ).execute()
        print(f"[Drive 上傳成功] {filename}")

    except Exception as e:
        print(f"[Drive 上傳失敗] {e}")

# ── 應用初始化 ────────────────────────────────────────────────────────
app = FastAPI(title="WISE AI 訪談系統")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions: dict = {}

# ── 資料模型 ──────────────────────────────────────────────────────────
class StartRequest(BaseModel):
    department: str
    graduation_year: str
    current_job: str
    job_category: str
    career_transition_timing: str

class MessageRequest(BaseModel):
    session_id: str
    message: str

# ── 輔助函式 ──────────────────────────────────────────────────────────
def generate_participant_id() -> str:
    count = len(list(TRANSCRIPTS_DIR.glob("EDU-2026-*.md"))) + 1
    return f"EDU-2026-{count:03d}"

def build_context_message(background: dict) -> str:
    return (
        f"受訪者背景資料（系統提供，請據此開始訪談）：\n"
        f"- 畢業系所：{background['department']}\n"
        f"- 畢業年份：{background['graduation_year']}\n"
        f"- 目前職業類別：{background['job_category']}\n"
        f"- 目前職位描述：{background['current_job']}\n"
        f"- 進入非典型職涯時間點：{background['career_transition_timing']}\n\n"
        f"請立即開始訪談。先簡短自我介紹（說明你是 AI 訪談員、研究目的、約 20-30 分鐘），然後從主題一開始提問。"
    )

def gemini_chat(history: list, new_message: str) -> str:
    contents = []
    for msg in history:
        gemini_role = "model" if msg["role"] == "assistant" else "user"
        contents.append(types.Content(
            role=gemini_role,
            parts=[types.Part(text=msg["content"])],
        ))
    contents.append(types.Content(
        role="user",
        parts=[types.Part(text=new_message)],
    ))

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=INTERVIEW_SYSTEM_PROMPT,
            max_output_tokens=600,
            temperature=0.7,
        ),
    )
    return response.text

def save_transcript(session_id: str):
    session = sessions.get(session_id)
    if not session:
        return

    participant_id = session["participant_id"]
    background     = session["background"]
    history        = session["history"]
    start_time     = session["start_time"]
    duration_min   = int((datetime.now() - start_time).total_seconds() / 60)

    dialogue_lines = []
    for msg in history:
        role    = "AI" if msg["role"] == "assistant" else "受訪者"
        content = msg["content"].replace("<<INTERVIEW_COMPLETE>>", "").strip()
        dialogue_lines.append(f"**{role}**：{content}\n")

    transcript = (
        f"# 訪談逐字稿\n"
        f"**受訪者代號**：{participant_id}\n"
        f"**訪談日期**：{datetime.now().strftime('%Y-%m-%d')}\n"
        f"**對話時長**：{duration_min} 分鐘\n"
        f"**畢業系所**：{background['department']}\n"
        f"**畢業年份**：{background['graduation_year']}\n"
        f"**目前職業類別**：{background['job_category']}\n"
        f"**目前職位描述**：{background['current_job']}\n\n"
        f"---\n\n"
        f"## 對話記錄\n\n"
        + "".join(dialogue_lines)
    )

    filename = f"{participant_id}.md"

    # 本地存檔
    (TRANSCRIPTS_DIR / filename).write_text(transcript, encoding="utf-8")
    print(f"[逐字稿已儲存] {filename}")

    # Google Drive 上傳
    upload_to_drive(filename, transcript)

# ── API 路由 ──────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.post("/api/start")
async def start_interview(req: StartRequest):
    session_id     = str(uuid.uuid4())
    participant_id = generate_participant_id()
    background     = req.dict()

    sessions[session_id] = {
        "participant_id": participant_id,
        "background":     background,
        "history":        [],
        "start_time":     datetime.now(),
        "is_complete":    False,
    }

    context_msg = build_context_message(background)
    ai_message  = gemini_chat([], context_msg)

    sessions[session_id]["history"].append({"role": "assistant", "content": ai_message})

    is_complete      = "<<INTERVIEW_COMPLETE>>" in ai_message
    ai_message_clean = ai_message.replace("<<INTERVIEW_COMPLETE>>", "").strip()

    if is_complete:
        sessions[session_id]["is_complete"] = True
        save_transcript(session_id)

    return {
        "session_id":     session_id,
        "participant_id": participant_id,
        "message":        ai_message_clean,
        "is_complete":    is_complete,
    }

@app.post("/api/chat")
async def chat(req: MessageRequest):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session 不存在或已過期")
    if session["is_complete"]:
        raise HTTPException(status_code=400, detail="此訪談已結束")

    session["history"].append({"role": "user", "content": req.message})

    ai_message = gemini_chat(session["history"][:-1], req.message)
    session["history"].append({"role": "assistant", "content": ai_message})

    is_complete      = "<<INTERVIEW_COMPLETE>>" in ai_message
    ai_message_clean = ai_message.replace("<<INTERVIEW_COMPLETE>>", "").strip()

    if is_complete:
        session["is_complete"] = True
        save_transcript(req.session_id)

    return {"message": ai_message_clean, "is_complete": is_complete}

app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
