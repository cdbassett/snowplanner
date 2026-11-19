from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0004_add_region_notes')]

    initial = False

    operations = [
        ops.CreateModel(
            name='RegionArea',
            fields=[
                ('area_id', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=8)),
                ('seq', fields.SmallIntField()),
                ('region_id', fields.CharField(max_length=5)),
                ('region', fields.CharField(max_length=100)),
                ('area', fields.CharField(max_length=100)),
                ('abbrev', fields.CharField(max_length=20)),
            ],
            options={'table': 'region_area', 'app': 'models', 'pk_attr': 'area_id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='TruckInfo',
            fields=[
                ('id', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=70)),
                ('kind', fields.CharField(max_length=10)),
                ('ui_key', fields.CharField(max_length=100)),
                ('name', fields.CharField(null=True, max_length=255)),
                ('truck_type', fields.CharField(default='', max_length=20)),
            ],
            options={'table': 'truck_info', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
