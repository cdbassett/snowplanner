from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0003_add_plan_legs')]

    initial = False

    operations = [
        ops.CreateModel(
            name='RegionNote',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('region', fields.CharField(unique=True, max_length=100)),
                ('text', fields.TextField(default='')),
            ],
            options={'table': 'region_note', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
