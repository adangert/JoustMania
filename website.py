from flask import Flask

app = Flask(__name__)

@app.route('/')
def index():
    return 'Joustmania!'

def start():
    app.run(host='0.0.0.0', port=80, debug=True)
