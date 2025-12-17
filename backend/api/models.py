from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class ResourceType(models.Model):
    """Resource types that flow through conduits.

    Base types are fixed (energy, compute, mechanical).
    Subtypes are flexible (electrical, quantum, hydraulic, etc.).
    """
    BASE_TYPES = [
        ('energy', 'Energy'),
        ('compute', 'Compute'),
        ('mechanical', 'Mechanical'),
    ]

    name = models.CharField(max_length=50, unique=True)  # "electrical", "quantum"
    base_type = models.CharField(max_length=20, choices=BASE_TYPES)

    def __str__(self):
        return f"{self.name} ({self.base_type})"


class Spaceship(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='spaceships')
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.owner.username})"

    def is_locked(self):
        """Ship is locked when any job is actively running."""
        return self.jobs.filter(paused_at__isnull=True, completed_at__isnull=True).exists()

    def compute_resource_flow(self):
        """Compute available resource flow through the node graph.

        PLACEHOLDER: Currently returns empty dict.

        TODO: Implement actual flow computation considering:
        - Part supplies (with min/max/variability from stats)
        - Part demands
        - Conduit capacity and efficiency
        - Graph connectivity (nodes must be connected via conduits)
        """
        return {}


class Node(models.Model):
    """A node in the spaceship's resource graph.

    Nodes define the graph topology. Parts attach to nodes.
    Conduits connect nodes to allow resource flow.

    Node types:
        mount - External mount point for swappable parts (mining arm, camera, etc.)
        internal - Internal node for fixed infrastructure (power routing, etc.)
    """
    NODE_TYPES = [
        ('mount', 'Mount Point'),
        ('internal', 'Internal'),
    ]

    spaceship = models.ForeignKey(Spaceship, on_delete=models.CASCADE, related_name='nodes')
    node_type = models.CharField(max_length=20, choices=NODE_TYPES)
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} ({self.node_type})"


class Part(models.Model):
    """A part attached to a node on a spaceship.

    Parts provide functionality and can supply or demand resources.
    Behavior is determined by part_type + stats.

    stats JSON structure:
        supplies: {resource_name: {"base": float, "variability": float}}
        demands: {resource_name: float}

    Example generator:
        {"supplies": {"electrical": {"base": 100, "variability": 0.1}}}

    Example mining arm:
        {"demands": {"mechanical": 50}}
    """
    node = models.OneToOneField(Node, on_delete=models.CASCADE, related_name='part')
    name = models.CharField(max_length=100)
    part_type = models.CharField(max_length=50)
    stats = models.JSONField(default=dict)

    def __str__(self):
        return f"{self.name} ({self.part_type})"

    @property
    def spaceship(self):
        return self.node.spaceship

    def get_behavior(self):
        """Get the behavior class instance for this part type.

        PLACEHOLDER: Behavior classes not yet implemented.

        TODO: Create behavior classes that handle type-specific logic
        like activation, status queries, resource production/consumption.
        """
        return None


class Conduit(models.Model):
    """An edge in the node graph that transfers resources.

    Conduits connect nodes and allow resource flow. They are typed
    to a specific resource and can be upgraded for better capacity/efficiency.
    """
    spaceship = models.ForeignKey(Spaceship, on_delete=models.CASCADE, related_name='conduits')
    from_node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='outputs')
    to_node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='inputs')
    resource_type = models.ForeignKey(ResourceType, on_delete=models.CASCADE)
    capacity = models.FloatField()  # max flow per second
    efficiency = models.FloatField(default=1.0)  # 0.85 = 15% loss
    level = models.IntegerField(default=1)  # upgrade level

    def __str__(self):
        return f"{self.from_node.name} -> {self.to_node.name} ({self.resource_type.name})"


class Job(models.Model):
    """A task running on a spaceship.

    Jobs use lazy evaluation - progress is computed on query based on
    elapsed time and resource flow, not via background ticks.

    While a job is running, the ship is locked (no part/conduit changes).
    """
    spaceship = models.ForeignKey(Spaceship, on_delete=models.CASCADE, related_name='jobs')
    job_type = models.CharField(max_length=50)  # "mining", "manufacturing", etc.
    started_at = models.DateTimeField()
    paused_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration = models.FloatField()  # base duration in seconds at full resource flow
    params = models.JSONField(default=dict)  # job-specific parameters
    demands = models.JSONField(default=dict)  # {resource_name: flow_per_second}
    result = models.JSONField(null=True, blank=True)  # stored on completion

    def __str__(self):
        return f"{self.job_type} on {self.spaceship.name}"

    def get_progress(self):
        """Compute current job progress (0.0 to 1.0).

        PLACEHOLDER: Currently uses simple elapsed/duration calculation.

        TODO: Implement proper resource-constrained progress:
        - Compute actual resource flow from ship's part graph
        - Rate = min(flow[r] / demands[r] for r in demands) as bottleneck
        - Track min flow, max flow for variability simulation
        - Simulate randomness: with variable supply, job might succeed
          or fail based on "luck" - if supply variability is high,
          players can get lucky (job completes despite inconsistent supply)
          or unlucky (job fails despite usually-adequate supply)
        - Consider storing random seed at job start for deterministic replay
        """
        if self.completed_at:
            return 1.0

        if self.paused_at:
            elapsed = (self.paused_at - self.started_at).total_seconds()
        else:
            elapsed = (timezone.now() - self.started_at).total_seconds()

        # PLACEHOLDER: Assumes full resource flow (rate = 1.0)
        # Real implementation should compute rate from resource graph
        rate = 1.0

        return min(1.0, elapsed * rate / self.duration)

    def check_completion(self):
        """Check if job is complete and finalize if so.

        PLACEHOLDER: Currently just checks progress >= 1.0.

        TODO: When implementing variability simulation:
        - Run the random simulation to determine if job succeeded
        - Store success/failure in result
        - Handle partial completion for failed jobs
        """
        if self.completed_at:
            return True

        if self.get_progress() >= 1.0:
            self.completed_at = timezone.now()
            self.result = {"status": "completed"}  # PLACEHOLDER
            self.save()
            return True

        return False
