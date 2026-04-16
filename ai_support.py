import config
import logging
from aiogram import types
from aiogram.fsm.context import FSMContext
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential
from base import get_instruction

# Инициализация клиента
client = ChatCompletionsClient(
    endpoint="https://models.inference.ai.azure.com",
    credential=AzureKeyCredential(config.GITHUB_TOKEN),
)

async def handle_ai_support(message: types.Message, state: FSMContext, bot):
    """Функция обработки вопроса пользователя через нейросеть"""
    await bot.send_chat_action(message.chat.id, "typing")
    user_query = message.text
    instruction = get_instruction()
    try:
        response = client.complete(
            messages=[
                SystemMessage(content=instruction),
                UserMessage(content=user_query),
            ],
            model="gpt-4o",
            temperature=0.7,
        )
        answer = response.choices[0].message.content
        await message.answer(f"🤖 **Ответ нейросети:**\n\n{answer}", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"AI Error: {e}")
        await message.answer("❌ Извините, нейросеть сейчас недоступна. Попробуйте позже.")
    await state.clear()