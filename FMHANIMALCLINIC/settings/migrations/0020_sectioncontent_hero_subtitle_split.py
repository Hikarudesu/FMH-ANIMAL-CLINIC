from django.db import migrations, models


def split_hero_subtitle(apps, schema_editor):
    SectionContent = apps.get_model('settings', 'SectionContent')

    try:
        hero = SectionContent.objects.get(section_type='HERO')
    except SectionContent.DoesNotExist:
        return

    if hero.subtitle_prefix or hero.subtitle_highlight:
        return

    subtitle = (hero.subtitle or '').strip()
    if not subtitle:
        return

    marker = 'AI Diagnostics'
    marker_index = subtitle.find(marker)

    if marker_index >= 0:
        hero.subtitle_prefix = subtitle[:marker_index].strip()
        hero.subtitle_highlight = marker
    else:
        hero.subtitle_prefix = subtitle
        hero.subtitle_highlight = ''

    hero.save(update_fields=['subtitle_prefix', 'subtitle_highlight'])


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0019_remove_veterinarian_branch_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='sectioncontent',
            name='subtitle_highlight',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='sectioncontent',
            name='subtitle_prefix',
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.RunPython(split_hero_subtitle, migrations.RunPython.noop),
    ]
