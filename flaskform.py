from flask import Flask, render_template
from wtforms import Form, widgets, SelectMultipleField

SECRET_KEY = 'development'

app = Flask(__name__)
app.config.from_object(__name__)

class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class SimpleForm(Form):
    string_of_files = ['one\r\ntwo\r\nthree\r\n']
    list_of_files = string_of_files[0].split()
    # create a list of value/description tuples
    files = [(x, x) for x in list_of_files]
    example = MultiCheckboxField('Label', choices=files)

@app.route('/',methods=['post','get'])
def hello_world():
    form = SimpleForm()
    if form.validate_on_submit():
        print(form.example.data)
    else:
        print(form.errors)
    return render_template('example.html',form=form)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=True)