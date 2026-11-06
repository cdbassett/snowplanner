from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0001_initial')]

    initial = False

    operations = [
        ops.CreateModel(
            name='DeliveryPlan',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('name', fields.CharField(max_length=100)),
                ('region', fields.CharField(max_length=100)),
                ('completed', fields.BooleanField(default=False)),
                ('visible', fields.BooleanField(default=False)),
                ('created', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'delivery_plan', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='PlanStop',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('plan', fields.ForeignKeyField('models.DeliveryPlan', source_field='plan_id', db_constraint=True, to_field='id', related_name='stops', on_delete=OnDelete.CASCADE)),
                ('position', fields.IntField()),
                ('area_id', fields.CharField(max_length=8)),
                ('x', fields.SmallIntField()),
                ('y', fields.SmallIntField()),
                ('map_item_id', fields.CharField(null=True, max_length=70)),
                ('label', fields.CharField(default='', max_length=255)),
                ('completed', fields.BooleanField(default=False)),
            ],
            options={'table': 'plan_stop', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='PlanCargo',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('stop', fields.ForeignKeyField('models.PlanStop', source_field='stop_id', db_constraint=True, to_field='id', related_name='cargo', on_delete=OnDelete.CASCADE)),
                ('action', fields.CharField(max_length=7)),
                ('kind', fields.CharField(default='cargo', max_length=7)),
                ('name', fields.CharField(max_length=255)),
                ('count', fields.SmallIntField(default=1)),
                ('ref_id', fields.CharField(null=True, max_length=70)),
            ],
            options={'table': 'plan_cargo', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
