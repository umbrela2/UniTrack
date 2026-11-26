from datetime import date, datetime

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime, parse_time
from rest_framework.exceptions import ValidationError

from .models import (
    Enseignant,
    Etudiant,
    Groupe,
    Module,
    Presence,
    Salle,
    Seance,
)

ENTITY_ALIASES = {
    'groupe': 'groupes',
    'groupes': 'groupes',
    'group': 'groupes',
    'groups': 'groupes',
    'module': 'modules',
    'modules': 'modules',
    'salle': 'salles',
    'salles': 'salles',
    'room': 'salles',
    'rooms': 'salles',
    'enseignant': 'enseignants',
    'enseignants': 'enseignants',
    'teacher': 'enseignants',
    'teachers': 'enseignants',
    'etudiant': 'etudiants',
    'etudiants': 'etudiants',
    'student': 'etudiants',
    'students': 'etudiants',
    'seance': 'seances',
    'seances': 'seances',
    'session': 'seances',
    'sessions': 'seances',
    'presence': 'presences',
    'presences': 'presences',
    'attendance': 'presences',
    'attendances': 'presences',
}

ENTITY_ORDER = [
    'groupes',
    'modules',
    'salles',
    'enseignants',
    'etudiants',
    'seances',
    'presences',
]


def _error(context, message):
    raise ValidationError({context: message})


def _as_items(value, bucket):
    if isinstance(value, dict):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        _error(bucket, 'Une liste ou un objet JSON est attendu.')

    for item in items:
        if not isinstance(item, dict):
            _error(bucket, 'Chaque élément doit être un objet JSON.')

    return items


def _to_int(value, field, context):
    try:
        return int(value)
    except (TypeError, ValueError):
        _error(context, f'Le champ {field} doit être un entier.')


def _to_str(value, field, context):
    if not isinstance(value, str) or not value.strip():
        _error(context, f'Le champ {field} doit être une chaîne non vide.')
    return value.strip()


def _required_int(item, field, context):
    if field not in item or item[field] in (None, ''):
        _error(context, f'Champ requis : {field}.')
    return _to_int(item[field], field, context)


def _external_ref(item, name, context):
    for key in (f'{name}_id', f'{name}_external_id'):
        value = item.get(key)
        if value not in (None, ''):
            return _to_int(value, key, context)

    value = item.get(name)
    if isinstance(value, dict):
        nested = value.get('external_id', value.get('id'))
        if nested not in (None, ''):
            return _to_int(nested, f'{name}.external_id', context)
    elif value not in (None, '') and isinstance(value, int):
        return value

    return None


def _resolve(model, external_id, label, context):
    obj = model.objects.filter(external_id=external_id).first()
    if obj is None:
        _error(
            context,
            f'{label} avec external_id={external_id} introuvable.',
        )
    return obj


def _upsert_simple(model, item, context, converters):
    external_id = _required_int(item, 'external_id', context)
    existing = model.objects.filter(external_id=external_id).first()
    defaults = {}

    for field, converter in converters.items():
        value = item.get(field)
        if value not in (None, ''):
            defaults[field] = converter(value, field, context)
        elif existing is None:
            _error(context, f'Champ requis : {field}.')

    _, created = model.objects.update_or_create(
        external_id=external_id,
        defaults=defaults,
    )
    return created


def _upsert_groupe(item, context):
    return _upsert_simple(
        Groupe,
        item,
        context,
        {
            'numero': _to_int,
            'annee_etude': _to_int,
            'specialite': _to_str,
        },
    )


def _upsert_module(item, context):
    return _upsert_simple(
        Module,
        item,
        context,
        {
            'intitule': _to_str,
            'semestre': _to_str,
        },
    )


def _upsert_salle(item, context):
    return _upsert_simple(
        Salle,
        item,
        context,
        {'nom_salle': _to_str},
    )


def _upsert_enseignant(item, context):
    return _upsert_simple(
        Enseignant,
        item,
        context,
        {
            'nom': _to_str,
            'prenom': _to_str,
            'email': _to_str,
        },
    )


def _upsert_etudiant(item, context):
    external_id = _required_int(item, 'external_id', context)
    existing = Etudiant.objects.filter(external_id=external_id).first()
    defaults = {}

    for field in ('matricule', 'nom', 'prenom', 'email'):
        value = item.get(field)
        if value not in (None, ''):
            defaults[field] = _to_str(value, field, context)
        elif existing is None:
            _error(context, f'Champ requis : {field}.')

    groupe_external_id = _external_ref(item, 'groupe', context)
    if groupe_external_id is None:
        if existing is None:
            _error(context, 'Champ requis : groupe_id.')
    else:
        defaults['groupe'] = _resolve(
            Groupe,
            groupe_external_id,
            'Groupe',
            context,
        )

    _, created = Etudiant.objects.update_or_create(
        external_id=external_id,
        defaults=defaults,
    )
    return created


def _parse_date(value, field, context):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    parsed = parse_date(str(value))
    if parsed is None:
        _error(context, f'Format de date invalide pour {field} (YYYY-MM-DD).')
    return parsed


def _parse_time(value, field, context):
    parsed = parse_time(str(value))
    if parsed is None:
        _error(context, f'Format d\'heure invalide pour {field} (HH:MM).')
    return parsed


def _parse_datetime(value, field, context):
    parsed = parse_datetime(str(value))
    if parsed is None:
        _error(context, f'Format de date/heure invalide pour {field}.')
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _upsert_seance(item, context):
    external_id = _required_int(item, 'external_id', context)
    existing = Seance.objects.filter(external_id=external_id).first()
    defaults = {}

    date_value = item.get('date_seance')
    if date_value not in (None, ''):
        defaults['date_seance'] = _parse_date(
            date_value,
            'date_seance',
            context,
        )
    elif existing is None:
        _error(context, 'Champ requis : date_seance.')

    for field in ('heure_debut', 'heure_fin'):
        value = item.get(field)
        if value not in (None, ''):
            defaults[field] = _parse_time(value, field, context)
        elif existing is None:
            _error(context, f'Champ requis : {field}.')

    type_seance = item.get('type_seance')
    if type_seance not in (None, ''):
        if type_seance not in Seance.TypeSeance.values:
            _error(context, 'Valeur invalide pour type_seance.')
        defaults['type_seance'] = type_seance
    elif existing is None:
        _error(context, 'Champ requis : type_seance.')

    statut = item.get('statut')
    if statut not in (None, ''):
        if statut not in Seance.Statut.values:
            _error(context, 'Valeur invalide pour statut.')
        defaults['statut'] = statut
    elif existing is None:
        _error(context, 'Champ requis : statut.')

    references = (
        ('groupe', Groupe, 'Groupe'),
        ('module', Module, 'Module'),
        ('enseignant', Enseignant, 'Enseignant'),
        ('salle', Salle, 'Salle'),
    )
    for name, model, label in references:
        ref = _external_ref(item, name, context)
        if ref is None:
            if existing is None:
                _error(context, f'Champ requis : {name}_id.')
        else:
            defaults[name] = _resolve(model, ref, label, context)

    _, created = Seance.objects.update_or_create(
        external_id=external_id,
        defaults=defaults,
    )
    return created


def _upsert_presence(item, context):
    seance_external_id = _external_ref(item, 'seance', context)
    etudiant_external_id = _external_ref(item, 'etudiant', context)

    if seance_external_id is None:
        _error(context, 'Champ requis : seance_id.')
    if etudiant_external_id is None:
        _error(context, 'Champ requis : etudiant_id.')

    seance = _resolve(Seance, seance_external_id, 'Séance', context)
    etudiant = _resolve(Etudiant, etudiant_external_id, 'Étudiant', context)
    existing = Presence.objects.filter(
        seance=seance,
        etudiant=etudiant,
    ).first()
    defaults = {}

    statut_presence = item.get('statut_presence')
    if statut_presence not in (None, ''):
        if statut_presence not in Presence.StatutPresence.values:
            _error(context, 'Valeur invalide pour statut_presence.')
        defaults['statut_presence'] = statut_presence
    elif existing is None:
        _error(context, 'Champ requis : statut_presence.')

    date_value = item.get('date_enregistrement')
    if date_value not in (None, ''):
        defaults['date_enregistrement'] = _parse_datetime(
            date_value,
            'date_enregistrement',
            context,
        )

    _, created = Presence.objects.update_or_create(
        seance=seance,
        etudiant=etudiant,
        defaults=defaults,
    )
    return created


HANDLERS = {
    'groupes': _upsert_groupe,
    'modules': _upsert_module,
    'salles': _upsert_salle,
    'enseignants': _upsert_enseignant,
    'etudiants': _upsert_etudiant,
    'seances': _upsert_seance,
    'presences': _upsert_presence,
}


def _collect_bundles(payload):
    bundles = {}

    event_name = (
        payload.get('event')
        or payload.get('entity')
        or payload.get('type')
    )
    event_data = payload.get('data')
    if event_data is None:
        event_data = payload.get('payload')
    if event_data is None:
        event_data = payload.get('item')

    if isinstance(event_name, str) and event_data is not None:
        entity = event_name.split('.')[0].strip().lower()
        bucket = ENTITY_ALIASES.get(entity)
        if bucket is None:
            _error('event', f'Entité non reconnue : {event_name}.')
        bundles[bucket] = _as_items(event_data, bucket)

    for key, value in payload.items():
        bucket = ENTITY_ALIASES.get(str(key).strip().lower())
        if bucket is None:
            continue
        items = _as_items(value, bucket)
        if bucket in bundles:
            bundles[bucket].extend(items)
        else:
            bundles[bucket] = items

    if not bundles and isinstance(event_name, str) and 'external_id' in payload:
        entity = event_name.split('.')[0].strip().lower()
        bucket = ENTITY_ALIASES.get(entity)
        if bucket is not None:
            item = {
                key: value
                for key, value in payload.items()
                if key not in ('event', 'entity', 'type', 'source', 'timestamp')
            }
            bundles[bucket] = [item]

    if not bundles:
        _error(
            'detail',
            'Aucune entité reconnue dans le payload de synchronisation.',
        )

    return bundles


def process_sync_payload(payload):
    if not isinstance(payload, dict):
        _error('detail', 'Le payload doit être un objet JSON.')

    bundles = _collect_bundles(payload)
    created = {bucket: 0 for bucket in ENTITY_ORDER}
    updated = {bucket: 0 for bucket in ENTITY_ORDER}

    with transaction.atomic():
        for bucket in ENTITY_ORDER:
            handler = HANDLERS[bucket]
            for index, item in enumerate(bundles.get(bucket, [])):
                context = f'{bucket}[{index}]'
                was_created = handler(item, context)
                if was_created:
                    created[bucket] += 1
                else:
                    updated[bucket] += 1

    return {
        'created': created,
        'updated': updated,
        'total_processed': sum(created.values()) + sum(updated.values()),
    }
