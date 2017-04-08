from .app import start

def main():
    start(app_main)

def app_main(app):
    loop = app.loop
    loop.call_later(2, app.exit)
