"""Regras de nomes de pessoas e telefone nacional de contato."""
import re
import unicodedata


class PersonValidationError(ValueError):
    def __init__(self, fields):
        self.fields = fields
        super().__init__(' '.join(fields.values()))


def validate_person_contact(name, phone, *, prefix=''):
    name = unicodedata.normalize('NFC', str(name or '').strip())
    phone = str(phone or '').strip()
    errors = {}
    if not name:
        errors[prefix + 'nome'] = 'Informe o nome completo.'
    elif len(name) > 160 or not any(c.isalpha() for c in name) or any(
        unicodedata.category(c)[0] not in 'LM' and c not in " .-'’" for c in name
    ):
        errors[prefix + 'nome'] = 'Nome deve conter apenas letras, espaços, apóstrofos, pontos ou hífens, sem números (máximo de 160 caracteres).'
    digits = re.sub(r'[^0-9]', '', phone)
    if phone and (len(phone) > 15 or not re.fullmatch(r'[0-9()\s-]+', phone) or not re.fullmatch(r'[1-9][0-9](?:[0-9]{8}|9[0-9]{8})', digits)):
        errors[prefix + 'telefone'] = 'Informe o DDD e 8 dígitos para fixo ou 9 para celular iniciado em 9 (10 ou 11 dígitos ao todo, sem +55).'
    if errors:
        raise PersonValidationError(errors)
    return name, phone or None
