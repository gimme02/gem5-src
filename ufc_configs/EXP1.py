import argparse
from gem5.resources.resource import AbstractResource
from pathlib import Path

from m5.objects import (
    L2XBar,
)

# Define the custom local resource class
class LocalBinaryResource(AbstractResource):
    def __init__(self, local_path: str):
        self.local_path = Path(local_path).resolve()

    def get_local_path(self):
        return str(self.local_path)  # Ensure the path is returned as a string


from gem5.isas import ISA
from gem5.utils.requires import requires
from gem5.resources.resource import obtain_resource
from gem5.components.memory import SingleChannelDDR3_1600
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.boards.abstract_board import AbstractBoard
from gem5.components.cachehierarchies.classic.caches.l1icache import L1ICache
from gem5.components.cachehierarchies.classic.caches.mmu_cache import MMUCache
from gem5.components.cachehierarchies.classic.caches.l1dcache import L1DCache
from gem5.components.cachehierarchies.classic.private_l1_cache_hierarchy import (
    PrivateL1CacheHierarchy,
)
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.components.processors.base_cpu_processor import BaseCPUProcessor
from gem5.components.processors.simple_core import SimpleCore
from gem5.simulate.simulator import Simulator

isa_choices = {
    "X86": ISA.X86,
    "Arm": ISA.ARM,
    "RiscV": ISA.RISCV,
}

# Setup the environment for RISC-V
requires(isa_required=ISA.X86)

parser = argparse.ArgumentParser(
    description="An example configuration script to run FDP."
)

# Arguments List
parser.add_argument(
    "--isa",
    type=str,
    default="X86",
    help="The ISA to simulate.",
    choices=isa_choices.keys(),
)

# Workload/Workload Arguments
parser.add_argument(
    "--workload",
    type=str,
    # default="/home/noyce20/8tb_ssd/riscv-vm/our_host_dir/benchmark-dhrystone/dhrystone",
    default="hello",
    help="give me workload binary path",
)

parser.add_argument(
    "--workload_args",
    nargs='+',
    type=str,
    # default="10000",
    default=[],
    help="give me workload arguments following the binary",
)

args = parser.parse_args()

# We use a single channel DDR3_1600 memory system
memory = SingleChannelDDR3_1600(size="8GB")

# We need a custom cache hierarchy to incorporate the FDP prefetcher.
class CacheHierarchy(PrivateL1CacheHierarchy):
    def __init__(self, icache, dcache):
        super().__init__(l1i_size="", l1d_size="")
        self.icache = icache
        self.dcache = dcache

    def incorporate_cache(self, board: AbstractBoard) -> None:

        # Set up the system port for functional access from the simulator.
        board.connect_system_port(self.membus.cpu_side_ports)

        for _, port in board.get_memory().get_mem_ports():
            self.membus.mem_side_ports = port

        cpu = board.get_processor().get_cores()[0]

        # Create and connect the instruction cache
        cpu.connect_icache(self.icache.cpu_side)
        self.icache.mem_side = self.membus.cpu_side_ports

        # Also the data cache
        cpu.connect_dcache(self.dcache.cpu_side)
        self.dcache.mem_side = self.membus.cpu_side_ports

        # Finally the cache for the MMU page walks
        self.mmucache = MMUCache(size="8KiB")
        self.mmucache.mem_side = self.membus.cpu_side_ports
        self.mmubus = L2XBar(width=64)
        self.mmubus.mem_side_ports = self.mmucache.cpu_side
        cpu.connect_walker_ports(
            self.mmubus.cpu_side_ports, self.mmubus.cpu_side_ports
        )

        if board.has_coherent_io():
            self._setup_io_cache(board)

        ## Connect the interrupt ports
        if board.get_processor().get_isa() == ISA.X86:
            cpu.connect_interrupt(
                self.membus.mem_side_ports, self.membus.cpu_side_ports
            )
        else:
            cpu.connect_interrupt()

processor = SimpleProcessor(
    cpu_type=CPUTypes.O3, isa=isa_choices[args.isa], num_cores=1
)
cpu = processor.cores[0].core

# Frontend Configurations
cpu.fetchWidth=8
cpu.decodeWidth = 8   # 디코드 폭 설정 (예: 한 사이클에 4개 디코드)
cpu.renameWidth = 8   # 리네임 폭 설정 (예: 한 사이클에 6개 리네임)

# Backend Configurations
cpu.LSQDepCheckShift = 4
cpu.LQEntries=72
cpu.SQEntries=48
cpu.forwardComSize=10
cpu.backComSize=10
cpu.numIQEntries=60
cpu.numROBEntries=192
cpu.issueWidth = 6
cpu.wbWidth = 12
cpu.commitWidth = 8
cpu.commitToFetchDelay = 1 #3 #10 #3
cpu.renameToIEWDelay=2
cpu.fetchToDecodeDelay=4 
cpu.numPhysIntRegs = 256  
cpu.numPhysFloatRegs = 256 

# Cache Configurations
icache = L1ICache(size="32kB", assoc=8)
dcache = L1DCache(size="32kB", assoc=8)
cache_hierarchy = CacheHierarchy(icache, dcache)

board = SimpleBoard(
    clk_freq="3GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

binary_resource = LocalBinaryResource(
    args.workload
    # "/home/noyce20/8tb_ssd/riscv-vm/our_host_dir/benchmark-dhrystone/dhrystone"  # Path to your compiled main binary
)

###gcc_r riscv benchmark. (jaewon)
#noyce20@noyce20-Escal:~/8tb_ssd/riscv-vm/our_host_dir$ sudo qemu-riscv64-static /home/noyce20/8tb_ssd/riscv-vm/our_host_dir/SPEC2017_riscv/SPEC2017/benchspec/CPU/502.gcc_r/run/run_base_refrate_mytest-m64.0001/cpugcc_r_base.mytest-m64 /home/noyce20/8tb_ssd/riscv-vm/our_host_dir/SPEC2017_riscv/SPEC2017/benchspec/CPU/502.gcc_r/run/run_base_refrate_mytest-m64.0001/gcc-pp.c 

# Setup the workload without any arguments (since main doesn't take arguments)
board.set_se_binary_workload(binary=binary_resource)
# board.set_se_binary_workload(binary=binary_resource,arguments=["10000"])

board.set_se_binary_workload(binary=binary_resource,arguments=args.workload_args)
# Lastly we run the simulation.
simulator = Simulator(board=board)
simulator.run()

print(
    "Exiting @ tick {} because {}.".format(
        simulator.get_current_tick(), simulator.get_last_exit_event_cause()
    )
)