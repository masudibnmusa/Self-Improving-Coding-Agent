from dataclasses import dataclass


@dataclass
class ResourceLimits:
    cpus: float = 2.0
    memory: str = "4g"
    pids: int = 512
    network: str = "none"
    command_timeout: int = 300

    @classmethod
    def from_config(cls, cfg):
        return cls(cfg.sandbox_cpus, cfg.sandbox_memory, cfg.sandbox_pids,
                   cfg.sandbox_network, cfg.command_timeout)

    def container_kwargs(self) -> dict:
        return {
            "nano_cpus": int(self.cpus * 1e9),
            "mem_limit": self.memory,
            "pids_limit": self.pids,
            "network_mode": self.network,
            "cap_drop": ["ALL"],
            "cap_add": ["DAC_OVERRIDE"],   # lets root write host-owned bind-mounted files
            "security_opt": ["no-new-privileges"],
        }