from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0007_add_objective_repair')]

    initial = False

    operations = [
        ops.AddField(model_name='ObjectiveRepair', name='damage_state', field=fields.SmallIntField(null=True)),
        ops.AddField(model_name='ObjectiveRepair', name='fuel_state', field=fields.SmallIntField(null=True)),
    ]
