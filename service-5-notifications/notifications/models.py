from django.db import models

class NotificationTemplate(models.Model):
    CODE_CHOICES = [
        ('ALERTE_3_ABS', 'Alerte Orange - 3 Absences'),
        ('EXCLUSION_5_ABS', 'Alerte Rouge - 5 Absences (Exclusion)'),
    ]
    code = models.CharField(max_length=30, choices=CODE_CHOICES, unique=True)
    sujet = models.CharField(max_length=200)
    corps = models.TextField()

    def __str__(self):
        return self.code


class NotificationPreference(models.Model):
    user_id = models.IntegerField(unique=True)
    user_email = models.EmailField()
    receive_email = models.BooleanField(default=True)
    receive_in_app = models.BooleanField(default=True)
    receive_push = models.BooleanField(default=False)

    def __str__(self):
        return f"Preferences User #{self.user_id}"


class NotificationHistory(models.Model):
    LEVEL_CHOICES = [
        ('WARNING', 'Alerte Orange (3 absences)'),
        ('DANGER', 'Alerte Rouge - Exclusion (5 absences)'),
    ]
    CHANNEL_CHOICES = [
        ('IN_APP', 'In-App'),
        ('EMAIL', 'Email'),
        ('PUSH', 'Push'),
    ]
    STATUS_CHOICES = [
        ('SENT', 'Envoyée'),
        ('FAILED', 'Échec'),
        ('READ', 'Lue'),
    ]

    etudiant_id = models.IntegerField()
    etudiant_nom = models.CharField(max_length=150)
    etudiant_email = models.EmailField()
    module_nom = models.CharField(max_length=150)
    nb_absences = models.IntegerField()
    
    niveau = models.CharField(max_length=15, choices=LEVEL_CHOICES)
    canal = models.CharField(max_length=15, choices=CHANNEL_CHOICES, default='EMAIL')
    statut = models.CharField(max_length=15, choices=STATUS_CHOICES, default='SENT')
    
    sujet = models.CharField(max_length=200)
    message = models.TextField()
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.statut}] {self.etudiant_nom} - {self.module_nom} ({self.nb_absences} abs)"