import argparse
import sys
from typing import Optional
from core.services import ResourceService

class CommandLineInterface:
    """
    CLI for AWS Tool.
    """
    def __init__(self, service: ResourceService):
        self.service = service

    def run(self, args: Optional[list] = None) -> None:
        parser = argparse.ArgumentParser(description="AWS Tool CLI")
        subparsers = parser.add_subparsers(dest="command", help="Available commands")

        # Command: list-vpcs
        parser_vpcs = subparsers.add_parser("list-vpcs", help="List all VPCs")
        parser_vpcs.add_argument("--region", default="us-west-2", help="AWS Region")

        # Command: list-subnets
        parser_subnets = subparsers.add_parser("list-subnets", help="List Subnets")
        parser_subnets.add_argument("--region", default="us-west-2", help="AWS Region")
        parser_subnets.add_argument("--vpc-id", help="Filter by VPC ID")

        # Command: list-instances
        parser_instances = subparsers.add_parser("list-instances", help="List EC2 Instances")
        parser_instances.add_argument("--region", default="us-west-2", help="AWS Region")

        # Parse
        if args is None:
            parsed_args = parser.parse_args()
        else:
            parsed_args = parser.parse_args(args)

        if not parsed_args.command:
            parser.print_help()
            return

        # Execute
        try:
            if parsed_args.command == "list-vpcs":
                self._handle_list_vpcs(parsed_args)
            elif parsed_args.command == "list-subnets":
                self._handle_list_subnets(parsed_args)
            elif parsed_args.command == "list-instances":
                self._handle_list_instances(parsed_args)
        except Exception as e:
            print(f"Error executing command: {e}", file=sys.stderr)

    def _handle_list_vpcs(self, args):
        print(f"Fetching VPCs for region: {args.region}...")
        vpcs = self.service.list_all_vpcs(args.region)
        if not vpcs:
            print("No VPCs found.")
            return
        
        print(f"{'VPC ID':<20} {'CIDR':<15} {'Name':<20} {'State'}")
        print("-" * 65)
        for vpc in vpcs:
            name = vpc.name if vpc.name else "-"
            print(f"{vpc.vpc_id:<20} {vpc.cidr_block:<15} {name:<20} {vpc.state}")

    def _handle_list_subnets(self, args):
        print(f"Fetching Subnets for region: {args.region} (VPC: {args.vpc_id if args.vpc_id else 'All'})...")
        subnets = self.service.list_subnets_for_vpc(args.region, args.vpc_id) if args.vpc_id else self.service.adapter.list_subnets(args.region)
        
        if not subnets:
            print("No Subnets found.")
            return

        print(f"{'Subnet ID':<20} {'CIDR':<15} {'AZ':<15} {'VPC ID':<20} {'Name'}")
        print("-" * 90)
        for sn in subnets:
            name = sn.name if sn.name else "-"
            print(f"{sn.subnet_id:<20} {sn.cidr_block:<15} {sn.availability_zone:<15} {sn.vpc_id:<20} {name}")

    def _handle_list_instances(self, args):
        print(f"Fetching Instances for region: {args.region}...")
        instances = self.service.list_instances(args.region)
        
        if not instances:
            print("No Instances found.")
            return

        print(f"{'Instance ID':<20} {'Type':<10} {'State':<12} {'Public IP':<15} {'Name'}")
        print("-" * 80)
        for inst in instances:
            name = inst.name if inst.name else "-"
            pub_ip = inst.public_ip if inst.public_ip else "-"
            print(f"{inst.instance_id:<20} {inst.instance_type:<10} {inst.state:<12} {pub_ip:<15} {name}")
