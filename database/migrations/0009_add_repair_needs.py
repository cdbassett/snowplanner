from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0008_add_repair_states')]

    initial = False

    operations = [
        ops.AddField(model_name='ObjectiveRepair', name='repair_points', field=fields.SmallIntField(null=True)),
        ops.AddField(model_name='ObjectiveRepair', name='fuel_liters', field=fields.SmallIntField(null=True)),
    ]
