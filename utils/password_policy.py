"""Politica para novas senhas; nao se aplica a autenticacao de senhas legadas."""
import re

PASSWORD_SYMBOLS = '.+-[]*~_#:?@'


def validate_new_password(password):
    if not isinstance(password, str) or not 8 <= len(password) <= 64:
        raise ValueError('A senha deve possuir entre 8 e 64 caracteres.')
    allowed = set(PASSWORD_SYMBOLS)
    if any(not (character.isascii() and character.isalnum())
           and character not in allowed for character in password):
        raise ValueError('Use letras, números e somente estes símbolos: . + - [ ] * ~ _ # : ? @ Sem espaços.')
    if not (re.search('[a-z]', password) and re.search('[A-Z]', password)
            and re.search('[0-9]', password) and any(c in allowed for c in password)):
        raise ValueError('A senha deve conter letra maiúscula, minúscula, número e símbolo.')
