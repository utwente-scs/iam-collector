import sys

from py2neo import Graph
import pandas as pd
import json


def load_excel(data_file):
    # Import the data from excel file as new dataframes
    output_dir = './output/'
    file_path = output_dir + data_file

    df_policies = pd.read_excel(file_path, sheet_name='policies', index_col=0)
    df_users = pd.read_excel(file_path, sheet_name='users', index_col=0)
    df_groups = pd.read_excel(file_path, sheet_name='groups', index_col=0)
    df_roles = pd.read_excel(file_path, sheet_name='roles', index_col=0)

    # Fill NaN (Not a Number) field with an empty string
    df_policies.fillna('', inplace=True)
    df_roles.columns = df_roles.columns.str.replace('.', '', regex=False)

    # Check if extra space was needed for the policy object, if so merge it again
    if 'ExtraPolicySpace' in df_policies.columns:
        for index, row in df_policies.iterrows():
            if row.ExtraPolicySpace != '':
                df_policies.at[index, 'PolicyObject'] = row.PolicyObject + row.ExtraPolicySpace

    return df_policies, df_users, df_groups, df_roles


def create_policy_nodes(gr, policies):
    tx = gr.begin()

    for index, row in policies.iterrows():
        tx.evaluate('''
        CREATE (policy:Policy {name: $name, id: $id, arn: $arn, policyObject: $policyObject}) RETURN policy
        ''', parameters={'name': row.PolicyName, 'id': row.PolicyId, 'arn': row.Arn,
                         'policyObject': row.PolicyObject})
    tx.commit()


def create_resource_nodes(gr, policies):
    tx = gr.begin()

    for index, row in policies.iterrows():
        policy_object = row.PolicyObject.replace("\'", "\"")
        policy_object = policy_object.replace("True", "true")
        policy_object = policy_object.replace("False", "false")

        try:
            policy_list = json.loads(policy_object)

            if not isinstance(policy_list, list):
                tmp = [policy_list]
                policy_list = tmp

            for policy in policy_list:

                # Check whether the policy actually contains resources
                if 'Resource' in policy:
                    resource_list = policy['Resource']

                    if not isinstance(resource_list, list):
                        tmp = [resource_list]
                        resource_list = tmp

                    for resource in resource_list:
                        tx.evaluate('''
                            MERGE (resource:Resource {name: $name, forPolicy: $policy})  
                            ''', parameters={'name': resource, 'policy': row.PolicyName})

                elif 'NotResource' in policy:
                    not_resource_list = policy['NotResource']

                    if not isinstance(not_resource_list, list):
                        tmp = [not_resource_list]
                        not_resource_list = tmp

                    for not_resource in not_resource_list:
                        tx.evaluate('''
                            MERGE (notresource:NotResource {name: $name, forPolicy: $policy})  
                            ''', parameters={'name': not_resource, 'policy': row.PolicyName})

        except:
            e = sys.exc_info()[0]
            print(policy_object)
            print(e)
            print('Error while loading: ' + row.PolicyName + 'and object: ' + policy_object)

    tx.commit()


def create_action_nodes(gr, policies):
    tx = gr.begin()

    for index, row in policies.iterrows():
        # Replace single quote with double quote for json parsing
        policy_object = row.PolicyObject.replace("\'", "\"")
        policy_object = policy_object.replace("True", "true")
        policy_object = policy_object.replace("False", "false")

        try:
            policy_list = json.loads(policy_object)

            if not isinstance(policy_list, list):
                tmp = [policy_list]
                policy_list = tmp

            for policy in policy_list:
                resource_list = []
                not_resource_list = []
                action_list = []
                not_action_list = []

                if 'Resource' in policy:
                    resource_list = policy['Resource']
                elif 'NotResource' in policy:
                    resource_list = policy['NotResource']

                if not isinstance(resource_list, list):
                    tmp = [resource_list]
                    resource_list = tmp

                if not isinstance(not_resource_list, list):
                    tmp = [not_resource_list]
                    not_resource_list = tmp

                if 'Action' in policy:
                    action_list = policy['Action']
                elif 'NotAction' in policy:
                    not_action_list = policy['NotAction']

                if not isinstance(action_list, list):
                    tmp = [action_list]
                    action_list = tmp

                if not isinstance(not_action_list, list):
                    tmp = [not_action_list]
                    not_action_list = tmp

                if resource_list and action_list:
                    for resource in resource_list:
                        for action in action_list:
                            tx.evaluate('''
                                MATCH (p:Policy), (res:Resource)  
                                WHERE p.name = $policyName AND res.name = $resourceName AND res.forPolicy = $policy
                                CREATE (p)-[:CONTAINS]->(action:Action {name: $name})-[:WORKS_ON]->(res)
                                RETURN action
                               ''', parameters={'policyName': row.PolicyName, 'resourceName': resource, 'name': action,
                                                'policy': row.PolicyName})

                if not_resource_list and action_list:
                    for resource in not_resource_list:
                        for action in action_list:
                            tx.evaluate('''
                                MATCH (p:Policy), (res:NotResource)  
                                WHERE p.name = $policyName AND res.name = $resourceName AND res.forPolicy = $policy
                                CREATE (p)-[:CONTAINS]->(action:NotAction {name: $name})-[:WORKS_NOT_ON]->(res)
                                RETURN action
                               ''', parameters={'policyName': row.PolicyName, 'resourceName': resource, 'name': action,
                                                'policy': row.PolicyName})

                if not_resource_list and not_action_list:
                    for resource in not_resource_list:
                        for action in not_action_list:
                            tx.evaluate('''
                                MATCH (p:Policy), (res:NotResource)  
                                WHERE p.name = $policyName AND res.name = $resourceName AND res.forPolicy = $policy
                                CREATE (p)-[:CONTAINS]->(action:notAction {name: $name})-[:WORKS_NOT_ON]->(res)
                                RETURN action
                               ''', parameters={'policyName': row.PolicyName, 'resourceName': resource, 'name': action,
                                                'policy': row.PolicyName})

                if resource_list and not_action_list:
                    for resource in resource_list:
                        for action in not_action_list:
                            tx.evaluate('''
                                MATCH (p:Policy), (res:Resource)  
                                WHERE p.name = $policyName AND res.name = $resourceName AND res.forPolicy = $policy
                                CREATE (p)-[:CONTAINS]->(action:NotAction {name: $name})-[:WORKS_NOT_ON]->(res)
                                RETURN action
                               ''', parameters={'policyName': row.PolicyName, 'resourceName': resource, 'name': action,
                                                'policy': row.PolicyName})

        except:
            print('Error while loading: ' + row.PolicyName + 'and object: ' + policy_object)

    tx.commit()


def create_user_nodes(gr, users):
    tx = gr.begin()

    for index, row in users.iterrows():
        tx.evaluate('''
            CREATE (user:User {name: $name, id: $id, arn: $arn, attachedPolicies: $attachedPolicies}) RETURN user
            ''', parameters={'name': row.UserName, 'id': row.UserId, 'arn': row.Arn,
                             'attachedPolicies': row.AttachedPolicies})
    tx.commit()

    tx = gr.begin()
    for index, row in users.iterrows():
        attached_policies = row.AttachedPolicies.replace("\'", "\"")
        attached_policies_list = json.loads(attached_policies)
        for policy in attached_policies_list:
            tx.evaluate('''
                MATCH (u:User), (p:Policy)
                WHERE u.name = $userName AND p.name = $policyName
                CREATE (p)-[:IS_ATTACHED_TO]->(u)
                ''', parameters={'userName': row.UserName, 'policyName': policy['PolicyName']})
    tx.commit()


def create_group_nodes(gr, groups):
    tx = gr.begin()

    for index, row in groups.iterrows():
        tx.evaluate('''
            CREATE (group:Group {name: $name, id: $id, arn: $arn, attachedPolicies: $attachedPolicies, user: $users}) RETURN group
            ''', parameters={'name': row.GroupName, 'id': row.GroupId, 'arn': row.Arn,
                             'attachedPolicies': row.AttachedPolicies, 'users': row.Users})
    tx.commit()

    tx = gr.begin()
    for index, row in groups.iterrows():
        attached_policies = row.AttachedPolicies.replace("\'", "\"")
        attached_policies_list = json.loads(attached_policies)
        for policy in attached_policies_list:
            tx.evaluate('''
                MATCH (g:Group), (p:Policy)
                WHERE g.name = $groupName AND p.name = $policyName
                CREATE (p)-[:IS_ATTACHED_TO]->(g)
                ''', parameters={'groupName': row.GroupName, 'policyName': policy['PolicyName']})
        tx.commit()
        tx = gr.begin()
        users = row.Users.replace("\'", "\"")
        users_list = json.loads(users)
        for user in users_list:
            tx.evaluate('''
                MATCH (u:User), (g:Group)
                WHERE u.name = $userName AND g.name = $groupName
                CREATE (u)-[:PART_OF]->(g)
                ''', parameters={'userName': user['UserName'], 'groupName': row.GroupName})
        tx.commit()


def create_role_nodes(gr, roles):
    tx = gr.begin()

    for index, row in roles.iterrows():
        tx.evaluate('''
            CREATE (role:Role {name: $name, id: $id, arn: $arn, attachedPolicies: $attachedPolicies, assumeRolePolicyDocumentVersion: $assumeRolePolicyDocumentVersion ,assumeRolePolicyDocumentStatement: $assumeRolePolicyDocumentStatement}) RETURN role
            ''', parameters={'name': row.RoleName, 'id': row.RoleId, 'arn': row.Arn,
                             'attachedPolicies': row.AttachedPolicies,
                             'assumeRolePolicyDocumentVersion': row.AssumeRolePolicyDocumentStatement,
                             'assumeRolePolicyDocumentStatement': row.AssumeRolePolicyDocumentStatement})
    tx.commit()

    tx = gr.begin()

    for index, row in roles.iterrows():
        attached_policies = row.AttachedPolicies.replace("\'", "\"")
        attached_policies_list = json.loads(attached_policies)
        for policy in attached_policies_list:
            tx.evaluate('''
                MATCH (r:Role), (p:Policy)
                WHERE r.name = $roleName AND p.name = $policyName
                CREATE (p)-[:IS_ATTACHED_TO]->(r)
                ''', parameters={'roleName': row.RoleName, 'policyName': policy['PolicyName']})
    tx.commit()


if __name__ == "__main__":
    graph = Graph("bolt://localhost:7687", user="neo4j", password="password")
    df_policies, df_users, df_groups, df_roles = load_excel("iam_policy_data_2021-04-09_10:15.xlsx")
    print('Start loading nodes')
    create_policy_nodes(graph, df_policies)
    print('Start loading resources')
    create_resource_nodes(graph, df_policies)
    print('Start loading actions')
    create_action_nodes(graph, df_policies)
    print('Start loading roles')
    create_role_nodes(graph, df_roles)
