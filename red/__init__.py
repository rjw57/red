from .app import Application

def main():
    app = Application()
    loop = app.loop

    loop.call_later(2, app.exit)

    app.run()
