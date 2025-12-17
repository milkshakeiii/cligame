"""Create a one-armed miner spaceship for a user.

Ship structure:
    - Central power source (internal) - supplies electrical energy
    - Mechanical mount (mount) - for mining arm
    - Compute mount (mount) - for camera/computing unit
    - Mechanical hub (internal) - routes mechanical from mount
    - Compute hub (internal) - routes compute, has data link to mechanical mount

Conduits (all bidirectional energy comes from center):
    - Power -> Mechanical hub (electrical)
    - Power -> Compute hub (electrical)
    - Mechanical hub -> Mechanical mount (mechanical)
    - Compute hub -> Compute mount (compute)
    - Compute hub -> Mechanical mount (data - for camera to control arm)
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from api.models import Spaceship, Node, Part, Conduit, ResourceType


class Command(BaseCommand):
    help = 'Create a one-armed miner spaceship for a user'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username to create ship for')
        parser.add_argument('--ship-name', type=str, default='Miner I', help='Name for the ship')

    def handle(self, *args, **options):
        username = options['username']
        ship_name = options['ship_name']

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stderr.write(f'User "{username}" does not exist')
            return

        # Ensure resource types exist
        electrical, _ = ResourceType.objects.get_or_create(
            name='electrical', defaults={'base_type': 'energy'}
        )
        mechanical, _ = ResourceType.objects.get_or_create(
            name='mechanical', defaults={'base_type': 'mechanical'}
        )
        classical_compute, _ = ResourceType.objects.get_or_create(
            name='classical', defaults={'base_type': 'compute'}
        )

        # Create the ship
        ship = Spaceship.objects.create(owner=user, name=ship_name)

        # Create nodes
        power_node = Node.objects.create(
            spaceship=ship, node_type='internal', name='Power Core'
        )
        mech_hub = Node.objects.create(
            spaceship=ship, node_type='internal', name='Mechanical Hub'
        )
        compute_hub = Node.objects.create(
            spaceship=ship, node_type='internal', name='Compute Hub'
        )
        mech_mount = Node.objects.create(
            spaceship=ship, node_type='mount', name='Mechanical Mount'
        )
        compute_mount = Node.objects.create(
            spaceship=ship, node_type='mount', name='Compute Mount'
        )

        # Create the power core part
        Part.objects.create(
            node=power_node,
            name='Basic Reactor',
            part_type='generator',
            stats={'supplies': {'electrical': {'base': 100, 'variability': 0.05}}}
        )

        # Create conduits
        # Power distribution
        Conduit.objects.create(
            spaceship=ship,
            from_node=power_node,
            to_node=mech_hub,
            resource_type=electrical,
            capacity=50,
            efficiency=0.95
        )
        Conduit.objects.create(
            spaceship=ship,
            from_node=power_node,
            to_node=compute_hub,
            resource_type=electrical,
            capacity=50,
            efficiency=0.95
        )

        # Mechanical routing
        Conduit.objects.create(
            spaceship=ship,
            from_node=mech_hub,
            to_node=mech_mount,
            resource_type=mechanical,
            capacity=40,
            efficiency=0.90
        )

        # Compute routing
        Conduit.objects.create(
            spaceship=ship,
            from_node=compute_hub,
            to_node=compute_mount,
            resource_type=classical_compute,
            capacity=30,
            efficiency=0.95
        )

        # Data link from compute hub to mechanical mount (for camera -> arm control)
        Conduit.objects.create(
            spaceship=ship,
            from_node=compute_hub,
            to_node=mech_mount,
            resource_type=classical_compute,
            capacity=10,
            efficiency=1.0  # data doesn't have loss
        )

        self.stdout.write(self.style.SUCCESS(
            f'Created "{ship_name}" for {username} with {ship.nodes.count()} nodes and {ship.conduits.count()} conduits'
        ))
