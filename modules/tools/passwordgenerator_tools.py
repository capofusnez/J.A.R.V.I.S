import random
import string
class PasswordGeneratorTools:
    def run(self, text: str = "") -> str:
        if text:
            length = int(text)
        else:
            length = 16
        characters = string.ascii_letters + string.digits + string.punctuation
        password = ''.join(random.choice(characters) for i in range(length))
        return password