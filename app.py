from flask import Flask, request, abort

from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
)

app = Flask(__name__)

line_bot_api = LineBotApi('FRFaoyZEeHnw0wBA3PD+tC4fF+VJUcUZpdrEGo3E//+qrsuSycW2eY+qiKDXmsUdBVZobBwB8nF9QVXrOYkBPMYHzvnPB8/CgY2sqmP4NGHSuYyNA/J7KQQ5Sls10WdI1JgWzVeZZ0BqYhRHnZa5sQdB04t89/1O/w1cDnyilFU=')
handler = WebhookHandler('d7633e6e779f6f3fe02dcc36530c4ff5')


@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=event.message.text))


if __name__ == "__main__":
    app.run()
