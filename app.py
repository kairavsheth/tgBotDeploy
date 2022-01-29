import os
import pickle
import re
import shutil
import threading

import pandas as pd
from flask import Flask, render_template, request
from flask_httpauth import HTTPBasicAuth
from telebot import TeleBot, Update
from telebot.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto
from werkzeug.security import check_password_hash, generate_password_hash

WEBHOOK_SSL_CERT = 'webhook_cert.pem'  # Path to the ssl certificate
WEBHOOK_SSL_PRIV = 'webhook_pkey.pem'  # Path to the ssl private key

app = Flask(__name__)
auth = HTTPBasicAuth()
bot = TeleBot('5085777113:AAHptWWZz_6KwyvlTCXPc2hMSvVw17pUU80')
fileErrors: list = []
botRunning: bool = False
temp: pd.DataFrame = None

try:
    with open('settings.bin', 'rb') as file_r:
        welcome_text: str = pickle.load(file_r)
        parents: list = pickle.load(file_r)
except FileNotFoundError:
    welcome_text: str = ''
    parents: list = []
    fileErrors.append('settings')

try:
    with open('categories.bin', 'rb') as file_r:
        categories: pd.DataFrame = pickle.load(file_r)
        file_r.close()
except FileNotFoundError:
    categories: pd.DataFrame = pd.DataFrame({'parent': [], 'category': []})
    fileErrors.append('categories')

try:
    with open('products.bin', 'rb') as file_r:
        products: pd.DataFrame = pickle.load(file_r)
        file_r.close()
except FileNotFoundError:
    products: pd.DataFrame = pd.DataFrame({'item': [], 'category': [], 'price': [], 'set': [], 'stock': []})
    fileErrors.append('products')


@auth.verify_password
def authorize(username, password):
    users = pickle.load(open('users.bin', 'rb'))
    if username in users and check_password_hash(users[username], password):
        return username


@app.route('/')
@auth.login_required
def statusPage():
    files = os.listdir('images')
    return render_template('status.html', missingImages=[row['item'] for i, row in products.iterrows() if
                                                         row.stock > 0 and not any([re.match(
                                                             r"{filename} ?(\(\d\))?.jpeg".format(filename=row['item']),
                                                             j) for j in files])],
                           hiddenCategories=categories[categories.parent == 'Hidden'].category.values)


@app.route('/update', methods=['GET', 'POST'])
@auth.login_required
def updatePage():
    if request.method == 'POST':
        global temp, products
        if request.form['stage'] == 'upload':
            if request.files['file'].filename.endswith('.csv'):
                temp = pd.read_csv(request.files['file'])
            elif request.files['file'].filename.endswith('.xls'):
                temp = pd.read_excel(request.files['file'])
            return render_template('columns.html', columns=temp.columns, saved=False)
        elif request.form['stage'] == 'columns':
            products = pd.DataFrame({i: temp[request.form[i]] for i in ['item', 'category', 'price', 'set', 'stock']})
            with open('products.bin', 'wb') as file_w:
                pickle.dump(products, file_w)
                file_w.close()
            return render_template('upload.html', message='Updated Items.')
    return render_template('upload.html')


@app.route('/categories', methods=['GET', 'POST'])
@auth.login_required
def categoriesPage():
    if request.method == 'POST':
        global categories
        response = {'category': [], 'parent': []}
        for i in request.form:
            response['category'].append(i)
            response['parent'].append(request.form[i])
        categories = pd.DataFrame(response)
        with open('categories.bin', 'wb') as file_w:
            pickle.dump(categories, file_w)
            file_w.close()
        return render_template('categories.html', message="Categories Updated.", parents=parents, new=[],
                               existing=categories)
    return render_template('categories.html', parents=parents, existing=categories,
                           new=[i for i in products.category.unique() if i not in categories.category.values])


@app.route('/settings', methods=['GET', 'POST'])
@auth.login_required
def settingsPage():
    if request.method == 'POST':
        global parents, welcome_text
        parents = list(set(request.form['parents'].split('\r\n')))
        welcome_text = request.form['welcome_text']
        with open('settings.bin', 'wb') as file_w:
            pickle.dump(welcome_text, file_w)
            pickle.dump(parents, file_w)
            file_w.close()
        return render_template('settings.html', message="Settings Updated.", parents=parents, welcome_text=welcome_text)
    return render_template('settings.html', parents=parents, welcome_text=welcome_text)


@app.route('/images', methods=['GET', 'POST'])
@auth.login_required
def imagesPage():
    if request.method == 'POST':
        uploaded_files = request.files.getlist("file")
        for i in uploaded_files:
            with open('images/{filename}'.format(filename=i.filename), 'wb') as img:
                shutil.copyfileobj(i.stream, img)
        return render_template('uploadImgs.html', message='Images uploaded.')
    return render_template('uploadImgs.html')


@app.route('/password', methods=['GET', 'POST'])
@auth.login_required
def passwordPage():
    if request.method == 'POST':
        users: dict = pickle.load(open('users.bin', 'rb'))
        if not check_password_hash(users[auth.current_user()], request.form['old']):
            return render_template('password.html', message='Old Password INCORRECT. Try again.')
        if not request.form['new'] == request.form['confirm']:
            return render_template('password.html',
                                   message='New Password and Confirm Password DO NOT MATCH. Try again.')
        users.update({auth.current_user(): generate_password_hash(request.form['new'])})
        pickle.dump(users, open('users.bin', 'wb'))
        return render_template('password.html', message='Password changed.')
    return render_template('password.html')


@app.route('webhook', methods=['POST'])
def webhook():
    if flask.request.headers.get('content-type') == 'application/json':
        json_string = flask.request.get_data().decode('utf-8')
        update = Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        flask.abort(403)


@bot.message_handler(commands=['start'])
def startChat(message: Message):
    keyboard = [[InlineKeyboardButton(text=i,
                                      callback_data=str({'parent': i, 'target': 'categories'}))] for i in parents]
    reply_markup = InlineKeyboardMarkup(keyboard)
    bot.send_message(message.chat.id, text='{welcome_text}\n\nPlease select the category to continue:'.format(
        welcome_text=welcome_text.format(sendername=message.from_user.first_name)),
                     reply_markup=reply_markup)


@bot.callback_query_handler(lambda callback: eval(callback.data)['target'] == 'parents')
def back(callback: CallbackQuery):
    keyboard = [[InlineKeyboardButton(text=i,
                                      callback_data=str({'parent': i, 'target': 'categories'}))] for i in parents]
    reply_markup = InlineKeyboardMarkup(keyboard)
    bot.edit_message_text(chat_id=callback.message.chat.id, message_id=callback.message.id,
                          text='{welcome_text}\n\nPlease select the category to continue:'.format(
                              welcome_text=welcome_text.format(sendername=callback.from_user.first_name)),
                          inline_message_id=callback.inline_message_id,
                          reply_markup=reply_markup)


@bot.callback_query_handler(lambda callback: eval(callback.data)['target'] == 'categories')
def showCategories(callback: CallbackQuery):
    parent = eval(callback.data)['parent']
    keyboard = [[InlineKeyboardButton(text=i,
                                      callback_data=str({'category': i, 'target': 'products'}))]
                for i in (categories[categories.parent == parent]).category]
    keyboard.append([InlineKeyboardButton(text='<<Back', callback_data=str({'target': 'parents'}))])
    reply_markup = InlineKeyboardMarkup(keyboard)

    bot.edit_message_text(chat_id=callback.message.chat.id, message_id=callback.message.id,
                          text='{welcome_text}\n\nCategory - {parent}'.format(
                              welcome_text=welcome_text.format(sendername=callback.from_user.first_name),
                              parent=parent),
                          inline_message_id=callback.inline_message_id,
                          reply_markup=reply_markup)


@bot.callback_query_handler(lambda callback: eval(callback.data)['target'] == 'products')
def sendImages(callback: CallbackQuery):
    category = eval(callback.data)['category']
    bot.edit_message_text(chat_id=callback.message.chat.id, message_id=callback.message.id,
                          text='{welcome_text}\n\nCategory - {category}'.format(
                              welcome_text=welcome_text.format(sendername=callback.from_user.first_name),
                              category=category),
                          inline_message_id=callback.inline_message_id,
                          reply_markup=None)

    for i, row in products[products.category == category].iterrows():
        if row.stock > 0:
            imgs = [InputMediaPhoto(media=open('images/{filename}'.format(filename=j), 'rb'), ) for j in
                    os.listdir('images') if
                    re.match(r"{filename} ?(\(\d\))?.jpeg".format(filename=row['item']), j)]
            if len(imgs) > 0:
                imgs[-1].caption = 'Price: ₹{price:.2F}\n{set} pcs/set'.format(price=row['price'], set=row['set'])
            while len(imgs) > 0:
                bot.send_media_group(chat_id=callback.message.chat.id, media=imgs[0:10])
                imgs = imgs[10:]

    bot.send_message(chat_id=callback.message.chat.id, text="--End of Product List--",
                     reply_markup=InlineKeyboardMarkup([
                         [InlineKeyboardButton(text='Previous Menu', callback_data=str(
                             {'parent': categories[categories.category == category].parent.values[0],
                              'target': 'categories'}))],
                         [InlineKeyboardButton(text='Main Menu', callback_data=str({'target': 'parents'}))]
                     ]))


@bot.message_handler()
def standard(message: Message):
    bot.send_message(chat_id=message.chat.id, text='Please send /start and use the buttons to operate the chatbot.')


class tgThread(threading.Thread):
    def run(self) -> None:
        bot.infinity_polling()


if __name__ == '__main__':
    bot.remove_webhook()

    time.sleep(0.1)

    # Set webhook
    bot.set_webhook(url='65.0.74.5/webhook',
                    certificate=open(WEBHOOK_SSL_CERT, 'r'))

    app.run(host='0.0.0.0', port=8080, ssl_context=(WEBHOOK_SSL_CERT, WEBHOOK_SSL_PRIV), debug=True)
