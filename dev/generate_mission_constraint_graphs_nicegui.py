#!/usr/bin/env python3
import itertools

from nicegui import ui

from snowrunner_utils import *


def main(region_filter, area_filter=None, guides=False):
    ed = get_english_lang_dict()

    def es(s):
        return ed.get(s) or s

    def write_graph(desc, added):
        id_gen = itertools.count(1)
        text_ids = defaultdict(lambda: str(next(id_gen)))
        connections = "\n".join(f'        {text_ids[a]}["{a}"]-->{text_ids[b]}["{b}"];' for a, b in added)
        ends, starts = set(map(itemgetter(0), added)), set(map(itemgetter(1), added))
        end_nodes = ",".join(text_ids[s] for s in starts - ends)
        start_nodes = ",".join(text_ids[s] for s in ends - starts)
        base_graph = f'''
    ```mermaid
    graph TD;
{connections}
    classDef end_node fill:#7fffd4,stroke:#666,stroke-width:2px;
    classDef start_node fill:#ffc0cb,stroke:#666,stroke-width:2px;
    class {end_nodes} end_node;
    class {start_nodes} start_node;

    ```
'''
        return base_graph

    def nl(s):
        return s
        parts = s.split()
        mid = len(parts) // 2
        return " ".join(parts[:mid]) + "\n" + " ".join(parts[mid:])

    def process_type(fname, region, area, objective_strings, objective_type, tasksSettings, added):
        for task_id, task in tasksSettings.items():
#            print(f"{indent}{task_id}: {Style.BRIGHT}{Fore.YELLOW}{ed[task_id]}{Style.RESET_ALL}")
#            print(f"{indent}{Style.BRIGHT}{Fore.YELLOW}{ed[task_id]}{Style.RESET_ALL}")
#            task_desc = f"{ed[task_id.upper()]} ({objective_type[0]})"
            task_desc, task_area = objective_strings[task_id.upper()]
            assert task_area == area
#            print(f"\t\t{task_desc}")
            a = nl(task_desc)
    #        ic(task)

            if (blockerObjectives := task.get("blockerObjectives")):
                for blockerObjective in blockerObjectives:
#                    blocker_desc = f"{ed[blockerObjective]} ({objective_type[0]})"
                    blocker_desc, blocker_area = objective_strings[blockerObjective]

                    if blocker_area != area:
                        blocker_desc += f" [{area_acronym(blocker_area)}]"

#                    print(f"\t\t\t{blockerObjective}: {blocker_desc}")
                    b = nl(blocker_desc)
                    added.append((a,b))


    def process_labels(area, objective_strings, objective_type, tasksSettings):
        for task_id, task in tasksSettings.items():
            objective_strings[task_id] = (f"{ed[task_id.upper()]} ({objective_type[0]})", area)


#    def make_desc(objective_type):
#        return f"{region} {area} {objective_type} Constraints"

#    indent = "\t\t"
    all_objective_strings = defaultdict(dict)

    for fname, python_data, region, area in iterate_objective_files(ed, region_filter): # no area filter bc depndencies may be in differnt area
        objective_strings = all_objective_strings[region]
        process_labels(area, objective_strings, "Task", python_data['tasksSettings'])
        process_labels(area, objective_strings, "Contract", python_data['contractsSettings'])

    for fname, python_data,region, area in iterate_objective_files(ed, region_filter, area_filter):
        objective_strings = all_objective_strings[region]

        print(f"{fname}: {': '.join(region_area(ed,fname))}:")

        desc = f"{region} {area} Constraints"
        added = []
#        print("\tTasks:")
        deliveries = process_type(fname, region, area, objective_strings, "Task", python_data['tasksSettings'], added)

#        print("\tContracts:")
        deliveries = process_type(fname, region, area, objective_strings, "Contract", python_data['contractsSettings'], added)
        md = write_graph(desc, added)
        print(md)
        ui.markdown(md, extras=['mermaid']).style('width: 90%; border: 2px solid black; border-radius: 8px; padding: 10px; height: 50vh')
        ui.run()
        break


if __name__ in {"__main__", "__mp_main__"}:
    parser = argparse.ArgumentParser(description="Show mission depndencies as a graph")
    add_region_area_args(parser, optional=False)
    args = parser.parse_args()

    main(args.region, args.area)

