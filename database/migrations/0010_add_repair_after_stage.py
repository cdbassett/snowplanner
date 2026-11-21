from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0009_add_repair_needs')]

    initial = False

    operations = [
        ops.AddField(model_name='ObjectiveRepair', name='after_stage', field=fields.CharField(null=True, max_length=20)),
    ]
