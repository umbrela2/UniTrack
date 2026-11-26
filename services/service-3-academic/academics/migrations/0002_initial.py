import academics.constraints
import django.contrib.postgres.constraints
import django.db.models.deletion
import django.db.models.expressions
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('academics', '0001_btree_gist'),
    ]

    operations = [
        migrations.CreateModel(
            name='Departement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=100, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Salle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom_salle', models.CharField(max_length=50, unique=True)),
                ('capacite', models.PositiveIntegerField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Module',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('intitule', models.CharField(max_length=150)),
                ('semestre', models.CharField(max_length=50)),
                ('departement', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='modules', to='academics.departement')),
            ],
            options={
                'unique_together': {('departement', 'intitule', 'semestre')},
            },
        ),
        migrations.CreateModel(
            name='Groupe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero', models.PositiveIntegerField()),
                ('annee_etude', models.CharField(max_length=20)),
                ('specialite', models.CharField(max_length=100)),
                ('departement', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='groupes', to='academics.departement')),
            ],
            options={
                'ordering': ['annee_etude', 'specialite', 'numero'],
                'unique_together': {('departement', 'annee_etude', 'specialite', 'numero')},
            },
        ),
        migrations.CreateModel(
            name='Seance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_seance', models.DateField()),
                ('heure_debut', models.TimeField()),
                ('heure_fin', models.TimeField()),
                ('type_seance', models.CharField(choices=[('COURS', 'Cours'), ('TD', 'TD'), ('TP', 'TP')], max_length=10)),
                ('statut', models.CharField(choices=[('PLANIFIEE', 'Planifiée'), ('EN_COURS', 'En cours'), ('CLOTUREE', 'Clôturée'), ('ANNULEE', 'Annulée'), ('NON_ASSUREE', 'Non assurée')], default='PLANIFIEE', max_length=15)),
                ('enseignant_id', models.PositiveIntegerField(db_index=True)),
                ('created_by', models.PositiveIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('groupe', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='seances', to='academics.groupe')),
                ('module', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='seances', to='academics.module')),
                ('salle', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='seances', to='academics.salle')),
            ],
            options={
                'ordering': ['date_seance', 'heure_debut'],
                'indexes': [models.Index(fields=['enseignant_id', 'date_seance'], name='academics_s_enseign_80e7a8_idx'), models.Index(fields=['groupe', 'date_seance'], name='academics_s_groupe__c61783_idx'), models.Index(fields=['statut', 'date_seance'], name='academics_s_statut_cd3c6a_idx')],
                'constraints': [models.CheckConstraint(condition=models.Q(('heure_fin__gt', models.F('heure_debut'))), name='seance_fin_apres_debut'), django.contrib.postgres.constraints.ExclusionConstraint(condition=models.Q(('statut', 'ANNULEE'), _negated=True), expressions=[(academics.constraints.TsRange(models.ExpressionWrapper(django.db.models.expressions.CombinedExpression(models.F('date_seance'), '+', models.F('heure_debut')), output_field=models.DateTimeField()), models.ExpressionWrapper(django.db.models.expressions.CombinedExpression(models.F('date_seance'), '+', models.F('heure_fin')), output_field=models.DateTimeField())), '&&'), ('enseignant_id', '=')], name='no_overlap_enseignant'), django.contrib.postgres.constraints.ExclusionConstraint(condition=models.Q(('statut', 'ANNULEE'), _negated=True), expressions=[(academics.constraints.TsRange(models.ExpressionWrapper(django.db.models.expressions.CombinedExpression(models.F('date_seance'), '+', models.F('heure_debut')), output_field=models.DateTimeField()), models.ExpressionWrapper(django.db.models.expressions.CombinedExpression(models.F('date_seance'), '+', models.F('heure_fin')), output_field=models.DateTimeField())), '&&'), ('salle', '=')], name='no_overlap_salle'), django.contrib.postgres.constraints.ExclusionConstraint(condition=models.Q(('statut', 'ANNULEE'), _negated=True), expressions=[(academics.constraints.TsRange(models.ExpressionWrapper(django.db.models.expressions.CombinedExpression(models.F('date_seance'), '+', models.F('heure_debut')), output_field=models.DateTimeField()), models.ExpressionWrapper(django.db.models.expressions.CombinedExpression(models.F('date_seance'), '+', models.F('heure_fin')), output_field=models.DateTimeField())), '&&'), ('groupe', '=')], name='no_overlap_groupe')],
            },
        ),
    ]
