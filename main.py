from fastapi import FastAPI, Request
import httpx
import os

app = FastAPI()

LINE_ACCESS_TOKEN = os.getenv("fbL8B+e8voao+f41Nx5DC9pT1GtsmwhlAQTN+rPFaNLQqPWCo7KyJmNNFMMAjIgc62xMfG4YQs/fzLjjTZTGF31q5+OshzTzI34aOw5KzLt2UFcm9LEi7KwgH5yZ4V6zjkudUdjEwCyxYQt6HELdBQdB04t89/1O/w1cDnyilFU=")
LINE_USER_ID = os.getenv("U4776c4283302343cebd85ab4cefbf2f9")

@app.post("/webhook")
async def receive_signal(request: Request):
    payload = await request.json()
    msg = payload.get("message", "🔔 มีสัญญาณเทรดใหม่!")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    body = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": msg}]
    }

    async with httpx.AsyncClient() as client:
        await client.post("https://api.line.me/v2/bot/message/push", headers=headers, json=body)

    return {"status": "ok"}
