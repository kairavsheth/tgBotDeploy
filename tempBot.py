from telebot import TeleBot
from telebot.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import flask
bot = TeleBot('5198887063:AAEvQ1xtqpeCO4vcx0QdY6KOOUDCkeMYA28')

chat_id = []


@bot.message_handler()
def standard(message: Message):
    bot.send_message(chat_id=message.chat.id, text='Starting next week... Stay tuned...')
    chat_id.append(message.chat.id)


if __name__ == '__main__':
    bot.infinity_polling()

