# test_async_gtasks_handler.py
import asyncio
import os
import pickle
import datetime
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from api_agent_classes import APIAction, APIActionType
from handlers.async_gtasks_handler import AsyncGoogleTasksAPIHandler
from handler_parameters.api_actions_params_gtasks import (
    TasksListTasklistsParams,
    TasksGetTasklistParams,
    TasksCreateTasklistParams,
    TasksUpdateTasklistParams,
    TasksDeleteTasklistParams,
    TasksListTasksParams,
    TasksGetTaskParams,
    TasksCreateTaskParams,
    TasksUpdateTaskParams,
    TasksDeleteTaskParams,
    TasksClearCompletedParams,
    TasksMoveTaskParams
)


def load_credentials():
    """Load and refresh Google API credentials"""
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save the refreshed token
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
        else:
            raise Exception("No valid credentials found. Run authentication script first.")

    return creds


async def test_list_tasklists():
    """Test listing all tasklists"""
    creds = load_credentials()

    async with AsyncGoogleTasksAPIHandler(creds) as handler:
        action = APIAction(
            action_type=APIActionType.TASKS_LIST_TASKLISTS,
            parameters={}
        )

        print("\n===== Testing List Tasklists =====")
        tasklists = await handler.perform_action(action)
        print(f"Found {len(tasklists)} tasklists:")
        for tasklist in tasklists:
            print(f"  - {tasklist.get('title')} ({tasklist.get('id')})")

        return tasklists


async def test_get_tasklist(tasklist_id):
    """Test getting a specific tasklist"""
    creds = load_credentials()

    async with AsyncGoogleTasksAPIHandler(creds) as handler:
        action = APIAction(
            action_type=APIActionType.TASKS_GET_TASKLIST,
            parameters={
                "tasklist_id": tasklist_id
            }
        )

        print(f"\n===== Testing Get Tasklist (ID: {tasklist_id}) =====")
        tasklist = await handler.perform_action(action)
        print(f"Tasklist details:")
        print(f"  - Title: {tasklist.get('title')}")
        print(f"  - ID: {tasklist.get('id')}")
        print(f"  - Updated: {tasklist.get('updated')}")

        return tasklist


async def test_create_tasklist():
    """Test creating a new tasklist"""
    creds = load_credentials()

    async with AsyncGoogleTasksAPIHandler(creds) as handler:
        # Create a tasklist with a timestamp to make it unique
        title = f"Test Tasklist {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        action = APIAction(
            action_type=APIActionType.TASKS_CREATE_TASKLIST,
            parameters={
                "title": title
            }
        )

        print(f"\n===== Testing Create Tasklist =====")
        tasklist = await handler.perform_action(action)
        print(f"Created tasklist:")
        print(f"  - Title: {tasklist.get('title')}")
        print(f"  - ID: {tasklist.get('id')}")

        return tasklist


async def test_update_tasklist(tasklist_id):
    """Test updating a tasklist's title"""
    creds = load_credentials()

    async with AsyncGoogleTasksAPIHandler(creds) as handler:
        # Update with a timestamp to make it unique
        new_title = f"Updated Tasklist {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        action = APIAction(
            action_type=APIActionType.TASKS_UPDATE_TASKLIST,
            parameters={
                "tasklist_id": tasklist_id,
                "new_title": new_title
            }
        )

        print(f"\n===== Testing Update Tasklist (ID: {tasklist_id}) =====")
        updated_tasklist = await handler.perform_action(action)
        print(f"Updated tasklist:")
        print(f"  - New Title: {updated_tasklist.get('title')}")
        print(f"  - ID: {updated_tasklist.get('id')}")
        print(f"  - Updated: {updated_tasklist.get('updated')}")

        return updated_tasklist


async def test_list_tasks(tasklist_id):
    """Test listing tasks from a tasklist"""
    creds = load_credentials()

    async with AsyncGoogleTasksAPIHandler(creds) as handler:
        action = APIAction(
            action_type=APIActionType.TASKS_LIST_TASKS,
            parameters={
                "tasklist_id": tasklist_id,
                "showCompleted": True,
                "showHidden": True
            }
        )

        print(f"\n===== Testing List Tasks (Tasklist ID: {tasklist_id}) =====")
        tasks = await handler.perform_action(action)

        print(f"Found {len(tasks)} tasks:")
        for task in tasks:
            status = "✓" if task.get('status') == 'completed' else "○"
            due = task.get('due', 'No due date')
            print(f"  - {status} {task.get('title')} (ID: {task.get('id')}, Due: {due})")

        return tasks


async def test_create_task(tasklist_id):
    """Test creating a new task in a tasklist"""
    creds = load_credentials()

    async with AsyncGoogleTasksAPIHandler(creds) as handler:
        # Set due date to tomorrow
        tomorrow = datetime.datetime.utcnow() + datetime.timedelta(days=1)
        tomorrow_str = tomorrow.strftime('%Y-%m-%dT%H:%M:%S.000Z')

        action = APIAction(
            action_type=APIActionType.TASKS_CREATE_TASK,
            parameters={
                "tasklist_id": tasklist_id,
                "title": f"Test Task {datetime.datetime.now().strftime('%H:%M:%S')}",
                "notes": "This is a test task created by the async handler",
                "due": tomorrow_str
            }
        )

        print(f"\n===== Testing Create Task (Tasklist ID: {tasklist_id}) =====")
        task = await handler.perform_action(action)
        print(f"Created task:")
        print(f"  - Title: {task.get('title')}")
        print(f"  - ID: {task.get('id')}")
        print(f"  - Due: {task.get('due')}")
        print(f"  - Notes: {task.get('notes')}")

        return task


async def test_get_task(tasklist_id, task_id):
    """Test getting a specific task"""
    creds = load_credentials()

    async with AsyncGoogleTasksAPIHandler(creds) as handler:
        action = APIAction(
            action_type=APIActionType.TASKS_GET_TASK,
            parameters={
                "tasklist_id": tasklist_id,
                "task_id": task_id
            }
        )

        print(f"\n===== Testing Get Task (ID: {task_id}) =====")
        task = await handler.perform_action(action)
        print(f"Task details:")
        print(f"  - Title: {task.get('title')}")
        print(f"  - ID: {task.get('id')}")
        print(f"  - Status: {task.get('status')}")
        print(f"  - Due: {task.get('due', 'Not set')}")
        print(f"  - Notes: {task.get('notes', 'None')}")

        return task


async def test_update_task(tasklist_id, task_id):
    """Test updating a task"""
    creds = load_credentials()

    async with AsyncGoogleTasksAPIHandler(creds) as handler:
        # Update the task with a new title and notes
        fields_to_update = {
            "title": f"Updated Task {datetime.datetime.now().strftime('%H:%M:%S')}",
            "notes": "This task was updated by the async handler"
        }

        action = APIAction(
            action_type=APIActionType.TASKS_UPDATE_TASK,
            parameters={
                "tasklist_id": tasklist_id,
                "task_id": task_id,
                "fields_to_update": fields_to_update
            }
        )

        print(f"\n===== Testing Update Task (ID: {task_id}) =====")
        updated_task = await handler.perform_action(action)
        print(f"Updated task:")
        print(f"  - New Title: {updated_task.get('title')}")
        print(f"  - ID: {updated_task.get('id')}")
        print(f"  - Notes: {updated_task.get('notes')}")

        return updated_task


async def test_complete_task(tasklist_id, task_id):
    """Test marking a task as completed"""
    creds = load_credentials()

    async with AsyncGoogleTasksAPIHandler(creds) as handler:
        # Update the task status to 'completed'
        fields_to_update = {
            "status": "completed"
        }

        action = APIAction(
            action_type=APIActionType.TASKS_UPDATE_TASK,
            parameters={
                "tasklist_id": tasklist_id,
                "task_id": task_id,
                "fields_to_update": fields_to_update
            }
        )

        print(f"\n===== Testing Complete Task (ID: {task_id}) =====")
        completed_task = await handler.perform_action(action)
        print(f"Completed task:")
        print(f"  - Title: {completed_task.get('title')}")
        print(f"  - ID: {completed_task.get('id')}")
        print(f"  - Status: {completed_task.get('status')}")
        print(f"  - Completed: {completed_task.get('completed', 'Not set')}")

        return completed_task


async def test_move_task(tasklist_id, task_id, previous=None):
    """Test moving a task within a tasklist"""
    creds = load_credentials()

    async with AsyncGoogleTasksAPIHandler(creds) as handler:
        action = APIAction(
            action_type=APIActionType.TASKS_MOVE_TASK,
            parameters={
                "tasklist_id": tasklist_id,
                "task_id": task_id,
                "previous": previous
            }
        )

        print(f"\n===== Testing Move Task (ID: {task_id}) =====")
        moved_task = await handler.perform_action(action)
        print(f"Moved task:")
        print(f"  - Title: {moved_task.get('title')}")
        print(f"  - ID: {moved_task.get('id')}")
        print(f"  - Position: {moved_task.get('position')}")

        return moved_task


async def test_clear_completed_tasks(tasklist_id):
    """Test clearing all completed tasks from a tasklist"""
    creds = load_credentials()

    async with AsyncGoogleTasksAPIHandler(creds) as handler:
        action = APIAction(
            action_type=APIActionType.TASKS_CLEAR_COMPLETED_TASKS,
            parameters={
                "tasklist_id": tasklist_id
            }
        )

        print(f"\n===== Testing Clear Completed Tasks (Tasklist ID: {tasklist_id}) =====")
        result = await handler.perform_action(action)
        print(f"Clear completed result: {result}")

        return result


async def test_delete_task(tasklist_id, task_id):
    """Test deleting a task"""
    creds = load_credentials()

    async with AsyncGoogleTasksAPIHandler(creds) as handler:
        action = APIAction(
            action_type=APIActionType.TASKS_DELETE_TASK,
            parameters={
                "tasklist_id": tasklist_id,
                "task_id": task_id
            }
        )

        print(f"\n===== Testing Delete Task (ID: {task_id}) =====")
        result = await handler.perform_action(action)
        print(f"Delete result: {result}")

        return result


async def test_delete_tasklist(tasklist_id):
    """Test deleting a tasklist"""
    creds = load_credentials()

    async with AsyncGoogleTasksAPIHandler(creds) as handler:
        action = APIAction(
            action_type=APIActionType.TASKS_DELETE_TASKLIST,
            parameters={
                "tasklist_id": tasklist_id
            }
        )

        print(f"\n===== Testing Delete Tasklist (ID: {tasklist_id}) =====")
        result = await handler.perform_action(action)
        print(f"Delete result: {result}")

        return result


async def test_parallel_requests():
    """Test executing multiple requests in parallel"""
    creds = load_credentials()

    async with AsyncGoogleTasksAPIHandler(creds) as handler:
        # Create multiple API action tasks
        print("\n===== Testing Parallel Requests =====")
        print("Starting parallel requests...")

        start_time = datetime.datetime.now()

        # Create tasks for parallel execution
        tasks = [
            # List all tasklists
            handler.perform_action(APIAction(
                action_type=APIActionType.TASKS_LIST_TASKLISTS,
                parameters={}
            )),

            # Get the default tasklist (usually '@default')
            handler.perform_action(APIAction(
                action_type=APIActionType.TASKS_GET_TASKLIST,
                parameters={"tasklist_id": "@default"}
            )),

            # List tasks from the default tasklist
            handler.perform_action(APIAction(
                action_type=APIActionType.TASKS_LIST_TASKS,
                parameters={
                    "tasklist_id": "@default",
                    "showCompleted": True
                }
            ))
        ]

        # Execute tasks concurrently
        results = await asyncio.gather(*tasks)

        end_time = datetime.datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        # Process results
        tasklists, default_tasklist, default_tasks = results

        print(f"Parallel requests completed in {execution_time:.2f} seconds")
        print(f"Found {len(tasklists)} tasklists")
        print(f"Default tasklist title: {default_tasklist.get('title')}")
        print(f"Found {len(default_tasks)} tasks in the default tasklist")

        return results


async def run_all_tests():
    """Run all tests in a logical sequence"""
    try:
        # List all tasklists
        tasklists = await test_list_tasklists()

        # Create a new tasklist specifically for testing
        print("\n----- Creating a fresh tasklist for testing -----")
        new_tasklist = await test_create_tasklist()
        test_tasklist_id = new_tasklist.get('id')

        # Get tasklist details
        await test_get_tasklist(test_tasklist_id)

        # Update the newly created tasklist
        await test_update_tasklist(test_tasklist_id)

        # For task operations, we'll use this test tasklist
        working_tasklist_id = test_tasklist_id

        # List tasks in the tasklist
        existing_tasks = await test_list_tasks(working_tasklist_id)

        # Create a new task
        new_task = await test_create_task(working_tasklist_id)
        task_id = new_task.get('id')

        # Wait a moment to ensure the task is fully processed
        await asyncio.sleep(2)

        # Get task details
        if task_id:
            await test_get_task(working_tasklist_id, task_id)

            # Update the task
            await test_update_task(working_tasklist_id, task_id)

            # Wait a moment to ensure the update is processed
            await asyncio.sleep(2)

            # If there are other tasks, try to move this one after another task
            if existing_tasks and len(existing_tasks) > 0:
                # Move task after the first existing task
                existing_task_id = existing_tasks[0].get('id')
                if existing_task_id and existing_task_id != task_id:
                    await test_move_task(working_tasklist_id, task_id, existing_task_id)

            # Mark the task as completed
            await test_complete_task(working_tasklist_id, task_id)

            # Wait a moment to ensure completion is processed
            await asyncio.sleep(2)

            # Clear completed tasks (including our new task)
            await test_clear_completed_tasks(working_tasklist_id)

            # Try to get the task after clearing (should still work)
            await test_get_task(working_tasklist_id, task_id)

            # Delete the task
            await test_delete_task(working_tasklist_id, task_id)

        # Create a temporary tasklist for deletion test
        temp_tasklist = await test_create_tasklist()
        temp_tasklist_id = temp_tasklist.get('id')

        # Wait a moment to ensure creation is processed
        await asyncio.sleep(2)

        # Delete the temporary tasklist
        if temp_tasklist_id:
            await test_delete_tasklist(temp_tasklist_id)

        # Run parallel request test
        await test_parallel_requests()

        print("\n===== All tests completed successfully =====")

    except Exception as e:
        print(f"\nError during tests: {e}")
        import traceback
        traceback.print_exc()


# Comparison test to show performance difference
async def comparison_test():
    """Compare performance of sequential vs parallel requests"""
    creds = load_credentials()

    print("\n===== Performance Comparison: Sequential vs Parallel =====")

    # Test sequential execution
    async with AsyncGoogleTasksAPIHandler(creds) as handler:
        print("Running sequential requests...")
        sequential_start = datetime.datetime.now()

        # Run requests one after another
        tasklists = await handler.perform_action(APIAction(
            action_type=APIActionType.TASKS_LIST_TASKLISTS,
            parameters={}
        ))

        default_tasklist = await handler.perform_action(APIAction(
            action_type=APIActionType.TASKS_GET_TASKLIST,
            parameters={"tasklist_id": "@default"}
        ))

        default_tasks = await handler.perform_action(APIAction(
            action_type=APIActionType.TASKS_LIST_TASKS,
            parameters={
                "tasklist_id": "@default",
                "showCompleted": True
            }
        ))

        sequential_end = datetime.datetime.now()
        sequential_time = (sequential_end - sequential_start).total_seconds()

        print(f"Sequential execution completed in {sequential_time:.2f} seconds")

    # Test parallel execution
    async with AsyncGoogleTasksAPIHandler(creds) as handler:
        print("Running parallel requests...")
        parallel_start = datetime.datetime.now()

        # Create tasks for parallel execution
        tasks = [
            handler.perform_action(APIAction(
                action_type=APIActionType.TASKS_LIST_TASKLISTS,
                parameters={}
            )),

            handler.perform_action(APIAction(
                action_type=APIActionType.TASKS_GET_TASKLIST,
                parameters={"tasklist_id": "@default"}
            )),

            handler.perform_action(APIAction(
                action_type=APIActionType.TASKS_LIST_TASKS,
                parameters={
                    "tasklist_id": "@default",
                    "showCompleted": True
                }
            ))
        ]

        # Execute tasks concurrently
        results = await asyncio.gather(*tasks)

        parallel_end = datetime.datetime.now()
        parallel_time = (parallel_end - parallel_start).total_seconds()

        print(f"Parallel execution completed in {parallel_time:.2f} seconds")

    # Calculate and display improvement
    if sequential_time > 0:
        improvement = (sequential_time - parallel_time) / sequential_time * 100
        print(f"Parallel execution was {improvement:.2f}% faster")

    return {
        "sequential_time": sequential_time,
        "parallel_time": parallel_time
    }


if __name__ == "__main__":
    # Run all individual tests
    asyncio.run(run_all_tests())

    # Or just run the performance comparison
    # asyncio.run(comparison_test())

    # Or run specific tests
    # asyncio.run(test_list_tasklists())
    # asyncio.run(test_create_tasklist())

    # Test creating and updating a task
    # async def test_create_and_update():
    #     tasklists = await test_list_tasklists()
    #     if tasklists:
    #         tasklist_id = tasklists[0].get('id')
    #         new_task = await test_create_task(tasklist_id)
    #         task_id = new_task.get('id')
    #         await asyncio.sleep(2)  # Wait for creation to process
    #         if task_id:
    #             await test_update_task(tasklist_id, task_id)
    # asyncio.run(test_create_and_update())