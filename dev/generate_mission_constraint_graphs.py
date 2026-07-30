#!/usr/bin/env python3
import os
from pathlib import Path
from operator import itemgetter

import graphviz

from utilities import ReadFile
from snowrunner_utils import *


def main(region_filter, area_filter):
    ed = get_english_lang_dict()

    def es(s):
        return ed.get(s) or s

    def new_graph(desc):
        engine='sfdp' # Scalable Force-Directed Placement
#        engine='neato')
#        engine='dot') # results in very wide no short pngs
#        engine='osage') # clustered graphs
#        engine='fdp') # Force-Directed Placement
        dot = graphviz.Digraph(comment=desc, format='png',engine=engine, node_attr={'shape': 'box', 'style': 'filled', "color": 'lightblue'})
        dot.attr(size='22,14', ratio='fill')
#        dot.attr(ratio='fill')
        # Set graph attributes to prevent overlap
        # 'overlap="false"' handles node overlap
        # 'splines="true"' handles edge/node overlap by routing edges as splines
#        dot.attr(overlap='false', splines='true')
        dot.attr(overlap='false')
#        dot.attr(rankdir='TB') # default
#        dot.attr(splines='ortho') # orthogonal (90-degree angle) edges
#        dot.attr(K="0.2") # default=.3, constant for ideal edge length for fdp
#        dot.attr(defaultdist="1") # neato, The distance between nodes in separate connected components, default: 1+(avg. len)*sqrt(|V|), minimum: epsilon
#        dot.attr(len="0.5") # neato, fdp,  defalut=1, Preferred edge length, in inches
#        dot.attr(rankdir='LR', style='filled', color='lightblue', shape="box")
        dot.attr(rankdir='LR')

        return dot

    def write_graph(dot, desc, added):
        if 1:
            ends, starts = set(map(itemgetter(0), added)), set(map(itemgetter(1), added))
#            nodes = set(map(first_elem, added)) | set(map(second_elem, added))

            for s in starts - ends:
                dot.node(s, s, color='aquamarine')

            for s in ends - starts:
                dot.node(s, s, color='pink')

        dot.render(filename=make_snowrunner_doc_path(desc), view=False, cleanup=True)

    def nl(s):
        s = s.replace(":", " ")
        parts = s.split()
        mid = len(parts) // 2
        return " ".join(parts[:mid]) + "\n" + " ".join(parts[mid:])

    def process_type(fname, region, area, objective_strings, objective_type, tasksSettings, dot, added):
        for task_id, task in tasksSettings.items():
#            print(f"{indent}{task_id}: {Style.BRIGHT}{Fore.YELLOW}{ed[task_id]}{Style.RESET_ALL}")
#            print(f"{indent}{Style.BRIGHT}{Fore.YELLOW}{ed[task_id]}{Style.RESET_ALL}")
#            task_desc = f"{ed[task_id.upper()]} ({objective_type[0]})"
#            task_desc, task_area = objective_strings.get(task_id.upper()) or task_id
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
#                    if not blockerObjective.endswith("task_id"):
#                        ic(task_id, blockerObjective)
#                        raise Exception("Mismatch")
                    b = nl(blocker_desc)
                    dot.edge(a, b)
                    added.append((a,b))


    def process_type_and_graph(fname, region, area, objective_strings, objective_type, tasksSettings):
        desc = f"{region} {area} {objective_type} Constraints.generated"
        dot = new_graph(desc)
        process_type(fname, region, area, objective_strings, objective_type, tasksSettings, dot)
        write_graph(dot, desc)


    def process_labels(area, objective_strings, objective_type, tasksSettings):
        for task_id, task in tasksSettings.items():
#            ic(task_id)
            objective_strings[task_id.upper()] = (f"{ed[task_id.upper()]} ({objective_type[0]})", area)


#    def make_desc(objective_type):
#        return f"{region} {area} {objective_type} Constraints"

#    indent = "\t\t"
    all_objective_strings = defaultdict(dict)

    for fname, python_data, region, area in iterate_objective_files(ed, region_filter, area_filter):
#        ic(region, area)
        objective_strings = all_objective_strings[region]
        process_labels(area, objective_strings, "Task", python_data['tasksSettings'])
        process_labels(area, objective_strings, "Contract", python_data['contractsSettings'])

    for fname, python_data,region, area in iterate_objective_files(ed, region_filter, area_filter):
        objective_strings = all_objective_strings[region]

        print(f"{fname}: {': '.join(region_area(ed,fname))}:")
#        python_data = parse_sso(ReadFile(os.path.join(snowrunner_initial_pak_dir, "[ps]", "us_12_04_objects.sso")))


        if 1:
            desc = f"{region} {area} Constraints"
            dot = new_graph(desc)
            added = []
#            print("\tTasks:")
            deliveries = process_type(fname, region, area, objective_strings, "Task", python_data['tasksSettings'], dot, added)

#            print("\tContracts:")
            deliveries = process_type(fname, region, area, objective_strings, "Contract", python_data['contractsSettings'], dot, added)
            write_graph(dot, desc, added)
        else:
            print("\tTasks:")
            deliveries = process_type_and_graph(fname, region, area, "Task", python_data['tasksSettings'])

            print("\tContracts:")
            deliveries = process_type_and_graph(fname, region, area, "Contract", python_data['contractsSettings'])

# To get the DOT source code string:
#    print(dot.source)


if __name__ == "__main__":
        parser = argparse.ArgumentParser(description="Parse objectives from gamefiles and generate constraint graphs (which missions depend on others)")
        add_region_area_args(parser)
        args = parser.parse_args()
        main(args.region, args.area)

