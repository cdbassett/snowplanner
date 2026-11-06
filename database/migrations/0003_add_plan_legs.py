from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0002_add_delivery_plans')]

    initial = False

    operations = [
        ops.CreateModel(
            name='PlanLeg',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('split_stop', fields.ForeignKeyField('models.PlanStop', source_field='split_stop_id', db_constraint=True, to_field='id', related_name='legs', on_delete=OnDelete.CASCADE)),
                ('number', fields.SmallIntField()),
                ('name', fields.CharField(default='', max_length=100)),
            ],
            options={'table': 'plan_leg', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='PlanLegCargo',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('leg', fields.ForeignKeyField('models.PlanLeg', source_field='leg_id', db_constraint=True, to_field='id', related_name='cargo', on_delete=OnDelete.CASCADE)),
                ('kind', fields.CharField(default='cargo', max_length=7)),
                ('name', fields.CharField(max_length=255)),
                ('count', fields.SmallIntField(default=1)),
                ('ref_id', fields.CharField(null=True, max_length=70)),
            ],
            options={'table': 'plan_leg_cargo', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.AddField(
            model_name='PlanStop',
            name='leg',
            field=fields.ForeignKeyField('models.PlanLeg', source_field='leg_id', null=True, db_constraint=True, to_field='id', related_name='stops', on_delete=OnDelete.CASCADE),
        ),
    ]
