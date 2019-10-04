from qflask.app import Flask

app = Flask()


@app.route("/", methods=["POST"])
def helloworld():
    return {"status": "success"}


if __name__ == "__main__":
    app.run("0.0.0.0", port=5000)
