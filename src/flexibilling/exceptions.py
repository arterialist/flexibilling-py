"""Exception hierarchy for billing decisions and storage failures."""


class BillingError(Exception):
    """Base class for expected billing-domain errors."""


class InsufficientFundsError(BillingError):
    """A billable rule matched but no target asset has enough balance."""

    def __init__(self, customer_id: object, service: object) -> None:
        self.customer_id = customer_id
        self.service = str(getattr(service, "value", service))
        super().__init__(
            f"Customer {customer_id} has insufficient funds for service '{self.service}'"
        )


class NoBillableUsageError(BillingError):
    """No rule applied because filters missed or every calculated cost was zero."""

    def __init__(self, customer_id: object, service: object) -> None:
        self.customer_id = customer_id
        self.service = str(getattr(service, "value", service))
        super().__init__(f"No billable usage for customer {customer_id} service '{self.service}'")


class RuleNotFoundError(BillingError):
    """No active billing rule exists for a service."""

    def __init__(self, service: object) -> None:
        self.service = str(getattr(service, "value", service))
        super().__init__(f"No active billing rules found for service '{self.service}'")


class GatekeeperDeniedError(BillingError):
    """The fast balance gate denied an operation."""

    def __init__(self, customer_id: object) -> None:
        self.customer_id = customer_id
        super().__init__(f"Gatekeeper denied: customer {customer_id} cannot transact")


class BillingConfigurationError(BillingError):
    """A configurable integration point was not supplied by the host backend."""


class BillingContextError(BillingError):
    """A decorator could not resolve a customer from the current call."""
