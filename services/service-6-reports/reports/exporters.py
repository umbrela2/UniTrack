from io import BytesIO
from xml.sax.saxutils import escape

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from rest_framework.exceptions import ValidationError

from .models import Presence, Seance
from .utils import (
    build_attendance_totals,
    build_by_module,
    build_students_at_risk,
    filter_sessions,
    get_active_thresholds,
    parse_date_param,
    parse_int_param,
)

REPORT_TYPE_LABELS = {
    'attendance_summary': "Synthèse d'assiduité",
    'students_at_risk': 'Étudiants à risque',
    'non_assured_sessions': 'Séances non assurées',
}

REPORT_TYPES = tuple(REPORT_TYPE_LABELS)

HEADER_COLOR = '#1B4F72'
HEADER_ARGB = 'FF1B4F72'
HEADER_FILL = PatternFill(
    start_color='1B4F72',
    end_color='1B4F72',
    fill_type='solid',
)
ALT_FILL = PatternFill(
    start_color='EAF2F8',
    end_color='EAF2F8',
    fill_type='solid',
)
KPI_FILL = PatternFill(
    start_color='D6EAF8',
    end_color='D6EAF8',
    fill_type='solid',
)
THIN_BORDER = Border(
    left=Side(style='thin', color='B7C9D6'),
    right=Side(style='thin', color='B7C9D6'),
    top=Side(style='thin', color='B7C9D6'),
    bottom=Side(style='thin', color='B7C9D6'),
)


def resolve_report_type(params):
    report_type = (params.get('report_type') or 'attendance_summary').strip()
    if report_type not in REPORT_TYPE_LABELS:
        raise ValidationError({
            'report_type': (
                'Valeur invalide. Valeurs acceptées : '
                + ', '.join(REPORT_TYPES)
                + '.'
            ),
        })
    return report_type


def build_filters_summary(params):
    filters = []
    module_id = parse_int_param(params, 'module_id')
    groupe_id = parse_int_param(params, 'groupe_id')
    enseignant_id = parse_int_param(params, 'enseignant_id')
    date_from = parse_date_param(params, 'date_from')
    date_to = parse_date_param(params, 'date_to')

    if module_id is not None:
        filters.append(f'Module : {module_id}')
    if groupe_id is not None:
        filters.append(f'Groupe : {groupe_id}')
    if enseignant_id is not None:
        filters.append(f'Enseignant : {enseignant_id}')
    if date_from is not None:
        filters.append(f'Du : {date_from.strftime("%d/%m/%Y")}')
    if date_to is not None:
        filters.append(f'Au : {date_to.strftime("%d/%m/%Y")}')

    return ' | '.join(filters) if filters else 'Aucun filtre'


def build_export_context(params):
    report_type = resolve_report_type(params)
    filters_summary = build_filters_summary(params)
    seuil_alerte, seuil_exclusion = get_active_thresholds()

    sessions = Seance.objects.select_related(
        'module',
        'groupe',
        'enseignant',
        'salle',
    )
    sessions = filter_sessions(sessions, params)

    closed_sessions = sessions.filter(statut=Seance.Statut.CLOTUREE)
    non_assured_sessions = (
        sessions.filter(statut=Seance.Statut.NON_ASSURREE)
        .select_related('module', 'groupe', 'enseignant', 'salle')
        .order_by('-date_seance', 'heure_debut')
    )

    presences = Presence.objects.filter(
        seance__in=closed_sessions
    ).select_related(
        'seance__module',
        'seance__groupe',
        'etudiant__groupe',
    )

    totals = build_attendance_totals(presences)
    risks, alert_count, exclusion_count = build_students_at_risk(
        presences,
        seuil_alerte,
        seuil_exclusion,
    )
    total_closed = closed_sessions.count()
    total_non_assured = non_assured_sessions.count()

    kpis = [
        ('Total Séances Clôturées', total_closed),
        ('Séances Non Assurées', total_non_assured),
        ("Taux d'Assiduité Global", f"{totals['taux_assiduite']} %"),
        ('Étudiants en Alerte', alert_count),
        ('Étudiants en Exclusion', exclusion_count),
    ]

    total_row = None
    if report_type == 'attendance_summary':
        headers = [
            'Module',
            'Séances clôturées',
            'Absences non justifiées',
            "Taux d'assiduité (%)",
        ]
        rows = [
            [
                row['module'],
                row['nb_seances'],
                row['total_absences'],
                row['taux_assiduite'],
            ]
            for row in build_by_module(closed_sessions, presences)
        ]
        if rows:
            total_row = [
                'TOTAL',
                total_closed,
                totals['absents'],
                totals['taux_assiduite'],
            ]
    elif report_type == 'students_at_risk':
        headers = [
            'Matricule',
            'Nom',
            'Prénom',
            'Groupe',
            'Module',
            'Absences non justifiées',
            'Niveau',
        ]
        rows = [
            [
                row['matricule'],
                row['nom'],
                row['prenom'],
                row['groupe'],
                row['module'],
                row['absences_non_justifiees'],
                row['niveau_alerte'],
            ]
            for row in risks
        ]
    else:
        headers = [
            'ID',
            'Date',
            'Début',
            'Fin',
            'Type',
            'Module',
            'Enseignant',
            'Groupe',
            'Salle',
        ]
        rows = [
            [
                seance.external_id,
                seance.date_seance.strftime('%d/%m/%Y'),
                seance.heure_debut.strftime('%H:%M'),
                seance.heure_fin.strftime('%H:%M'),
                seance.type_seance,
                seance.module.intitule,
                f'{seance.enseignant.nom} {seance.enseignant.prenom}',
                str(seance.groupe),
                seance.salle.nom_salle,
            ]
            for seance in non_assured_sessions
        ]

    generated_at = timezone.localtime(timezone.now()).strftime(
        '%d/%m/%Y à %H:%M'
    )

    return {
        'report_type': report_type,
        'report_label': REPORT_TYPE_LABELS[report_type],
        'headers': headers,
        'rows': rows,
        'total_row': total_row,
        'kpis': kpis,
        'filters_summary': filters_summary,
        'generated_at': generated_at,
        'seuil_alerte': seuil_alerte,
        'seuil_exclusion': seuil_exclusion,
    }


def build_excel_report(params):
    context = build_export_context(params)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = context['report_label'][:31]

    column_count = len(context['headers'])
    last_column = get_column_letter(column_count)
    title = "UniTrack - Université M'hamed Bougara Boumerdès"

    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=column_count)
    title_cell = sheet.cell(row=1, column=1, value=title)
    title_cell.font = Font(bold=True, size=16, color=HEADER_ARGB)
    title_cell.alignment = Alignment(horizontal='center', vertical='center')
    sheet.row_dimensions[1].height = 28

    sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=column_count)
    generated_cell = sheet.cell(
        row=2,
        column=1,
        value=(
            f"Généré le {context['generated_at']} "
            "(Africa/Algiers)"
        ),
    )
    generated_cell.font = Font(italic=True, size=10, color='566573')
    generated_cell.alignment = Alignment(horizontal='center')

    sheet.merge_cells(start_row=3, start_column=1, end_row=3, end_column=column_count)
    description_cell = sheet.cell(
        row=3,
        column=1,
        value=(
            f"Type de rapport : {context['report_label']}  |  "
            f"Filtres : {context['filters_summary']}"
        ),
    )
    description_cell.font = Font(size=10, color='34495E')
    description_cell.alignment = Alignment(horizontal='center')

    kpi_text = '   |   '.join(
        f'{label} : {value}' for label, value in context['kpis']
    )
    sheet.merge_cells(start_row=4, start_column=1, end_row=4, end_column=column_count)
    kpi_cell = sheet.cell(row=4, column=1, value=kpi_text)
    kpi_cell.font = Font(bold=True, size=10, color=HEADER_ARGB)
    kpi_cell.fill = KPI_FILL
    kpi_cell.alignment = Alignment(
        horizontal='center',
        vertical='center',
        wrap_text=True,
    )
    sheet.row_dimensions[4].height = 30

    header_row = 6
    for column_index, header in enumerate(context['headers'], start=1):
        cell = sheet.cell(
            row=header_row,
            column=column_index,
            value=header,
        )
        cell.font = Font(bold=True, color='FFFFFF', size=11)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(
            horizontal='center',
            vertical='center',
            wrap_text=True,
        )
        cell.border = THIN_BORDER

    data_rows = list(context['rows'])
    if context['total_row']:
        data_rows.append(context['total_row'])

    for row_offset, row_values in enumerate(data_rows):
        excel_row = header_row + 1 + row_offset
        is_total_row = (
            context['total_row'] is not None
            and row_offset == len(data_rows) - 1
        )
        for column_index, value in enumerate(row_values, start=1):
            cell = sheet.cell(
                row=excel_row,
                column=column_index,
                value=value,
            )
            cell.border = THIN_BORDER
            cell.alignment = Alignment(
                horizontal='center' if column_index > 1 else 'left',
                vertical='center',
                wrap_text=True,
            )
            if is_total_row:
                cell.font = Font(bold=True, color=HEADER_ARGB)
                cell.fill = KPI_FILL
            elif row_offset % 2 == 1:
                cell.fill = ALT_FILL

    for column_index in range(1, column_count + 1):
        max_length = len(str(context['headers'][column_index - 1]))
        for row_values in data_rows:
            max_length = max(
                max_length,
                len(str(row_values[column_index - 1])),
            )
        sheet.column_dimensions[
            get_column_letter(column_index)
        ].width = min(max(max_length + 3, 14), 42)

    if data_rows:
        sheet.auto_filter.ref = (
            f'A{header_row}:{last_column}{header_row + len(data_rows)}'
        )
    sheet.freeze_panes = f'A{header_row + 1}'
    sheet.page_setup.orientation = 'landscape'
    sheet.page_setup.fitToWidth = 1
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_title_rows = f'1:{header_row}'

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


def _pdf_styles():
    styles = getSampleStyleSheet()
    return {
        'republic': ParagraphStyle(
            'Republic',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=11,
            alignment=TA_CENTER,
            leading=14,
            spaceAfter=2,
        ),
        'university': ParagraphStyle(
            'University',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=13,
            alignment=TA_CENTER,
            leading=16,
            spaceAfter=2,
        ),
        'title': ParagraphStyle(
            'ReportTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=16,
            textColor=colors.HexColor(HEADER_COLOR),
            alignment=TA_CENTER,
            leading=20,
            spaceBefore=4,
            spaceAfter=2,
        ),
        'meta': ParagraphStyle(
            'ReportMeta',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            alignment=TA_CENTER,
            leading=12,
            textColor=colors.HexColor('#34495E'),
        ),
        'kpi_label': ParagraphStyle(
            'KpiLabel',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=7.5,
            alignment=TA_CENTER,
            leading=9,
            textColor=colors.white,
        ),
        'kpi_value': ParagraphStyle(
            'KpiValue',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=13,
            alignment=TA_CENTER,
            leading=16,
            textColor=colors.HexColor(HEADER_COLOR),
        ),
        'table_header': ParagraphStyle(
            'TableHeader',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8,
            alignment=TA_CENTER,
            leading=10,
            textColor=colors.white,
        ),
        'table_cell': ParagraphStyle(
            'TableCell',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=10,
        ),
        'empty': ParagraphStyle(
            'Empty',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=9,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#566573'),
        ),
        'thresholds': ParagraphStyle(
            'Thresholds',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor('#566573'),
        ),
    }


def _pdf_cell(value, style):
    return Paragraph(escape(str(value)), style)


def _pdf_table_widths(report_type):
    available = A4[0] - 3.2 * cm
    weights = {
        'attendance_summary': [4.0, 2.0, 2.4, 2.4],
        'students_at_risk': [1.6, 1.7, 1.7, 3.0, 2.6, 1.8, 1.4],
        'non_assured_sessions': [0.8, 1.6, 1.0, 1.0, 1.0, 2.6, 2.7, 2.7, 1.4],
    }[report_type]
    total_weight = sum(weights)
    return [available * weight / total_weight for weight in weights]


def _draw_pdf_footer(canvas, document):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#B7C9D6'))
    canvas.setLineWidth(0.4)
    canvas.line(1.6 * cm, 1.45 * cm, A4[0] - 1.6 * cm, 1.45 * cm)
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.HexColor('#566573'))
    canvas.drawString(
        1.6 * cm,
        1.0 * cm,
        "UniTrack - Rapport Officiel d'Assiduité",
    )
    canvas.drawRightString(
        A4[0] - 1.6 * cm,
        1.0 * cm,
        f'Page {document.page}',
    )
    canvas.restoreState()


def build_pdf_report(params):
    context = build_export_context(params)
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.8 * cm,
        title="UniTrack - Rapport Officiel d'Assiduité",
        author="UniTrack",
    )
    styles = _pdf_styles()
    story = []

    story.append(Paragraph(
        escape('République Algérienne Démocratique et Populaire'),
        styles['republic'],
    ))
    story.append(Paragraph(
        escape('Université M\'hamed Bougara – Boumerdès'),
        styles['university'],
    ))
    story.append(Paragraph(
        escape("UniTrack - Rapport Officiel d'Assiduité"),
        styles['title'],
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        escape(
            f"Généré le {context['generated_at']} (Africa/Algiers)"
        ),
        styles['meta'],
    ))
    story.append(Paragraph(
        escape(f"Type de rapport : {context['report_label']}"),
        styles['meta'],
    ))
    story.append(Paragraph(
        escape(f"Filtres : {context['filters_summary']}"),
        styles['meta'],
    ))
    story.append(Spacer(1, 14))

    kpi_labels = [
        _pdf_cell(label, styles['kpi_label'])
        for label, _ in context['kpis']
    ]
    kpi_values = [
        _pdf_cell(value, styles['kpi_value'])
        for _, value in context['kpis']
    ]
    kpi_table = Table(
        [kpi_labels, kpi_values],
        colWidths=[(A4[0] - 3.2 * cm) / 5] * 5,
        hAlign='CENTER',
    )
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(HEADER_COLOR)),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#EAF2F8')),
        ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor('#85C1E9')),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 14))

    table_data = [[
        _pdf_cell(header, styles['table_header'])
        for header in context['headers']
    ]]
    for row in context['rows']:
        table_data.append([
            _pdf_cell(value, styles['table_cell'])
            for value in row
        ])

    empty_rows = False
    if len(table_data) == 1:
        empty_rows = True
        table_data.append([
            _pdf_cell(
                'Aucune donnée disponible pour les filtres sélectionnés.',
                styles['empty'],
            )
            for _ in context['headers']
        ])

    if context['total_row']:
        table_data.append([
            _pdf_cell(value, styles['table_header'])
            for value in context['total_row']
        ])

    data_table = Table(
        table_data,
        colWidths=_pdf_table_widths(context['report_type']),
        repeatRows=1,
        hAlign='CENTER',
    )
    table_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(HEADER_COLOR)),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#AEB6BF')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [
            colors.white,
            colors.HexColor('#EAF2F8'),
        ]),
    ]
    if empty_rows:
        table_style.append(('SPAN', (0, 1), (-1, 1)))
    if context['total_row']:
        table_style.append((
            'BACKGROUND',
            (0, len(table_data) - 1),
            (-1, len(table_data) - 1),
            colors.HexColor('#D6EAF8'),
        ))
    data_table.setStyle(TableStyle(table_style))
    story.append(data_table)

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        escape(
            'Seuils actifs : alerte à partir de '
            f"{context['seuil_alerte']} absences, exclusion à partir de "
            f"{context['seuil_exclusion']} absences non justifiées."
        ),
        styles['thresholds'],
    ))

    document.build(
        story,
        onFirstPage=_draw_pdf_footer,
        onLaterPages=_draw_pdf_footer,
    )
    buffer.seek(0)
    return buffer
