import os
import secrets
import time
import uuid
from typing import List

import pytest

from literalai import AsyncLiteralClient, LiteralClient
from literalai.context import active_steps_var
from literalai.observability.generation import ChatGeneration, GenerationMessage
from literalai.observability.thread import Thread

"""
End to end tests for the SDK
By default this test suite won't run, you need to explicitly run it with the following command:
    pytest -m e2e

Those test require a $LITERAL_API_URL and $LITERAL_API_KEY environment variables to be set.
"""


@pytest.mark.e2e
class Teste2e:
    """
    Don't change the order of the tests, they are dependend on each other
    Those tests are not meant to be parallelized
    """

    @pytest.fixture(scope="session")
    def broken_client(self):
        url = "http://foo.bar"
        api_key = os.getenv("LITERAL_API_KEY", None)
        assert url is not None and api_key is not None, "Missing environment variables"

        client = LiteralClient(batch_size=5, url=url, api_key=api_key)
        yield client
        client.event_processor.flush_and_stop()

    @pytest.fixture(scope="session")
    def client(self):
        url = os.getenv("LITERAL_API_URL", None)
        api_key = os.getenv("LITERAL_API_KEY", None)
        assert url is not None and api_key is not None, "Missing environment variables"

        client = LiteralClient(batch_size=5, url=url, api_key=api_key)
        yield client
        client.event_processor.flush_and_stop()

    @pytest.fixture(scope="session")
    def staging_client(self):
        url = os.getenv("LITERAL_API_URL", None)
        api_key = os.getenv("LITERAL_API_KEY", None)
        assert url is not None and api_key is not None, "Missing environment variables"

        client = LiteralClient(
            batch_size=5, url=url, api_key=api_key, environment="staging"
        )
        yield client
        client.event_processor.flush_and_stop()

    @pytest.fixture(scope="session")
    def async_client(self):
        url = os.getenv("LITERAL_API_URL", None)
        api_key = os.getenv("LITERAL_API_KEY", None)
        assert url is not None and api_key is not None, "Missing environment variables"

        async_client = AsyncLiteralClient(batch_size=5, url=url, api_key=api_key)
        yield async_client
        async_client.event_processor.flush_and_stop()

    async def test_user(self, client: LiteralClient, async_client: AsyncLiteralClient):
        user = await async_client.api.create_user(
            identifier=f"test_user_{secrets.token_hex()}", metadata={"foo": "bar"}
        )
        assert user.id is not None
        assert user.metadata == {"foo": "bar"}

        updated_user = await async_client.api.update_user(
            id=user.id, metadata={"foo": "baz"}
        )
        assert updated_user.metadata == {"foo": "baz"}

        fetched_user = await async_client.api.get_user(id=user.id)
        assert fetched_user and fetched_user.id == user.id

        users = await async_client.api.get_users(first=1)
        assert len(users.data) == 1

        await async_client.api.delete_user(id=user.id)

        deleted_user = await async_client.api.get_user(id=user.id)
        assert deleted_user is None

    async def test_generation(
        self, client: LiteralClient, async_client: AsyncLiteralClient
    ):
        chat_generation = ChatGeneration(
            provider="test",
            model="test",
            messages=[
                {"content": "Hello", "role": "user"},
                {"content": "Hi", "role": "assistant"},
            ],
            tags=["test"],
        )
        generation = await async_client.api.create_generation(chat_generation)
        assert generation.id is not None

        generations = await async_client.api.get_generations(
            first=1, order_by={"column": "createdAt", "direction": "DESC"}
        )
        assert len(generations.data) == 1
        assert generations.data[0].id == generation.id

    async def test_thread(
        self, client: LiteralClient, async_client: AsyncLiteralClient
    ):
        user = await async_client.api.create_user(
            identifier=f"test_user_{secrets.token_hex()}"
        )
        thread = await async_client.api.create_thread(
            metadata={"foo": "bar"}, participant_id=user.id, tags=["hello"]
        )
        assert thread.id is not None
        assert thread.metadata == {"foo": "bar"}
        assert user.id
        assert thread.participant_id == user.id

        fetched_thread = await async_client.api.get_thread(id=thread.id)
        assert fetched_thread and fetched_thread.id == thread.id

        updated_thread = await async_client.api.update_thread(
            id=fetched_thread.id, tags=["hello:world"]
        )
        assert updated_thread.tags == ["hello:world"]

        threads = await async_client.api.get_threads(
            first=1, order_by={"column": "createdAt", "direction": "DESC"}
        )
        assert len(threads.data) == 1
        assert threads.data[0].id == thread.id

        threads = await async_client.api.list_threads(
            first=1, order_by={"column": "createdAt", "direction": "DESC"}
        )
        assert len(threads.data) == 1
        assert threads.data[0].id == thread.id

        await async_client.api.delete_thread(id=thread.id)
        await async_client.api.delete_user(id=user.id)

        deleted_thread = await async_client.api.get_thread(id=thread.id)
        assert deleted_thread is None

    async def test_step(self, client: LiteralClient, async_client: AsyncLiteralClient):
        thread = await async_client.api.create_thread()
        step = await async_client.api.create_step(
            thread_id=thread.id, metadata={"foo": "bar"}
        )
        assert step.id is not None
        assert step.thread_id == thread.id

        updated_step = await async_client.api.update_step(
            id=step.id, metadata={"foo": "baz"}, tags=["hello"]
        )
        assert updated_step.metadata == {"foo": "baz"}
        assert updated_step.tags == ["hello"]

        fetched_step = await async_client.api.get_step(id=step.id)
        assert fetched_step and fetched_step.id == step.id

        sent_step = await async_client.api.send_steps(steps=[step.to_dict()])
        assert len(sent_step["data"].keys()) == 1

        await async_client.flush()
        is_deleted = await async_client.api.delete_step(id=step.id)
        assert is_deleted is True, "Step should be deleted"
        time.sleep(1)

        deleted_step = await async_client.api.get_step(id=step.id)

        assert deleted_step is None

    async def test_steps(self, client: LiteralClient):
        thread = client.api.create_thread()
        step = client.api.create_step(
            thread_id=thread.id, tags=["to_score"], name="test"
        )
        assert step.id is not None

        steps = client.api.get_steps(
            first=1,
            filters=[{"field": "tags", "operator": "in", "value": ["to_score"]}],
        )
        assert len(steps.data) == 1
        assert steps.data[0].id == step.id

        client.api.delete_step(id=step.id)
        deleted_step = client.api.get_step(id=step.id)
        assert deleted_step is None

    async def test_score(self, client: LiteralClient, async_client: AsyncLiteralClient):
        thread = await async_client.api.create_thread()
        step = await async_client.api.create_step(
            thread_id=thread.id, metadata={"foo": "bar"}
        )

        assert step.id is not None

        score = await async_client.api.create_score(
            step_id=step.id,
            name="user-feedback",
            type="HUMAN",
            comment="hello",
            value=1,
        )
        assert score.id is not None
        assert score.comment == "hello"

        updated_score = await async_client.api.update_score(
            id=score.id, update_params={"value": 0}
        )
        assert updated_score.value == 0
        assert updated_score.comment == "hello"

        scores = await async_client.api.get_scores(
            first=1, order_by={"column": "createdAt", "direction": "DESC"}
        )
        assert len(scores.data) == 1
        assert scores.data[0].id == score.id

    async def test_attachment(
        self, client: LiteralClient, async_client: AsyncLiteralClient
    ):
        attachment_url = (
            "https://upload.wikimedia.org/wikipedia/commons/8/8f/Example_image.svg"
        )
        thread = await async_client.api.create_thread()
        step = await async_client.api.create_step(
            thread_id=thread.id, metadata={"foo": "bar"}
        )

        assert step.id is not None

        attachment = await async_client.api.create_attachment(
            url=attachment_url,
            step_id=step.id,
            thread_id=thread.id,
            name="foo",
            metadata={"foo": "bar"},
        )
        assert attachment.id is not None
        assert attachment.name == "foo"
        assert attachment.metadata == {"foo": "bar"}

        fetched_attachment = await async_client.api.get_attachment(id=attachment.id)
        assert fetched_attachment is not None
        assert fetched_attachment.id == attachment.id

        updated_attachment = await async_client.api.update_attachment(
            id=attachment.id, update_params={"name": "bar"}
        )
        assert updated_attachment.name == "bar"
        assert updated_attachment.metadata == {"foo": "bar"}

        await async_client.api.delete_attachment(id=attachment.id)
        deleted_attachment = await async_client.api.get_attachment(id=attachment.id)
        assert deleted_attachment is None

    async def test_ingestion(
        self, client: LiteralClient, async_client: AsyncLiteralClient
    ):
        with async_client.thread():
            with async_client.step(name="test_ingestion") as step:
                step.metadata = {"foo": "bar"}
                assert async_client.event_processor.event_queue._qsize() == 0
                stack = active_steps_var.get()
                assert stack is not None and len(stack) == 1

            assert async_client.event_processor.event_queue._qsize() == 1

        stack = active_steps_var.get()
        assert stack is not None and len(stack) == 0

    @pytest.mark.timeout(5)
    async def test_thread_decorator(
        self, client: LiteralClient, async_client: AsyncLiteralClient
    ):
        async def assert_delete(thread_id: str):
            thread = await async_client.api.get_thread(thread_id)
            assert thread.tags == ["foo"]
            assert thread.name == "test"
            assert await async_client.api.delete_thread(thread_id) is True

        @async_client.thread(tags=["foo"], name="test", metadata={"async": False})
        def thread_decorated():
            t = async_client.get_current_thread()
            assert t is not None
            assert t.tags == ["foo"]
            assert t.metadata == {"async": False}
            return t.id

        id = thread_decorated()
        await assert_delete(id)

        @async_client.thread(tags=["foo"], name="test", metadata={"async": True})
        async def a_thread_decorated():
            t = async_client.get_current_thread()
            assert t is not None
            assert t.tags == ["foo"]
            assert t.metadata == {"async": True}
            assert t.name == "test"
            return t.id

        id = await a_thread_decorated()
        await assert_delete(id)

    @pytest.mark.timeout(5)
    async def test_release(self):
        url = os.getenv("LITERAL_API_URL", None)
        api_key = os.getenv("LITERAL_API_KEY", None)
        async_client = AsyncLiteralClient(
            batch_size=5, url=url, api_key=api_key, release="test"
        )

        async def assert_delete(thread_id: str, step_id: str):
            await async_client.flush()
            assert await async_client.api.delete_step(step_id) is True
            assert await async_client.api.delete_thread(thread_id) is True

        @async_client.thread
        def thread_decorated():
            @async_client.step(name="foo", type="llm")
            def step_decorated():
                t = async_client.get_current_thread()
                s = async_client.get_current_step()
                assert s is not None
                assert s.name == "foo"
                assert s.type == "llm"
                assert s.metadata.get("release") == "test"
                return t.id, s.id

            return step_decorated()

        thread_id, step_id = thread_decorated()
        await assert_delete(thread_id, step_id)

    @pytest.mark.timeout(5)
    async def test_step_decorator(
        self, client: LiteralClient, async_client: AsyncLiteralClient
    ):
        async def assert_delete(thread_id: str, step_id: str):
            await async_client.flush()
            assert await async_client.api.delete_step(step_id) is True
            assert await async_client.api.delete_thread(thread_id) is True

        @async_client.thread
        def thread_decorated():
            @async_client.step(name="foo", type="llm", tags=["to_score"])
            def step_decorated():
                t = async_client.get_current_thread()
                s = async_client.get_current_step()
                assert s is not None
                assert s.name == "foo"
                assert s.type == "llm"
                assert s.tags == ["to_score"]
                return t.id, s.id

            return step_decorated()

        thread_id, step_id = thread_decorated()
        await assert_delete(thread_id, step_id)

        @async_client.thread
        async def a_thread_decorated():
            @async_client.step(name="foo", type="llm")
            async def a_step_decorated():
                t = async_client.get_current_thread()
                s = async_client.get_current_step()
                assert s is not None
                assert s.name == "foo"
                assert s.type == "llm"
                return t.id, s.id

            return await a_step_decorated()

        thread_id, step_id = await a_thread_decorated()
        await assert_delete(thread_id, step_id)

    @pytest.mark.timeout(5)
    async def test_run_decorator(
        self, client: LiteralClient, async_client: AsyncLiteralClient
    ):
        async def assert_delete(step_id: str):
            await async_client.flush()
            step = await async_client.api.get_step(step_id)
            assert step and step.output is not None
            assert await async_client.api.delete_step(step_id) is True

        @async_client.run(name="foo")
        def step_decorated():
            s = async_client.get_current_step()
            assert s is not None
            assert s.name == "foo"
            assert s.type == "run"
            root_run = async_client.get_current_root_run()
            assert root_run is not None
            assert root_run.name == "foo"
            return s.id

        step_id = step_decorated()
        await assert_delete(step_id)

    @pytest.mark.timeout(5)
    async def test_nested_run_steps(
        self, client: LiteralClient, async_client: AsyncLiteralClient
    ):
        @async_client.run(name="foo")
        def run_decorated():
            s = async_client.get_current_step()

            assert s is not None

            @async_client.run(name="foo")
            def nested_run_decorated():
                @async_client.step(type="tool")
                def step_decorated():
                    s = async_client.get_current_step()
                    assert s is not None
                    return s

                return step_decorated()

            return [s.id, nested_run_decorated()]

        id, step = run_decorated()
        assert id == step.root_run_id

    async def test_parallel_requests(self, async_client: AsyncLiteralClient):
        ids = []

        @async_client.thread
        def request():
            t = async_client.get_current_thread()
            ids.append(t.id)

        @async_client.thread
        async def async_request():
            t = async_client.get_current_thread()
            ids.append(t.id)

        request()
        request()
        await async_request()
        await async_request()

        assert len(ids) == len(set(ids))

    async def create_test_step(self, async_client: AsyncLiteralClient):
        thread = await async_client.api.create_thread()
        return await async_client.api.create_step(
            thread_id=thread.id,
            input={"content": "hello world!"},
            output={"content": "hello back!"},
        )

    @pytest.mark.timeout(5)
    async def test_dataset(self, async_client: AsyncLiteralClient):
        dataset_name = str(uuid.uuid4())
        step = await self.create_test_step(async_client)
        dataset = await async_client.api.create_dataset(
            name=dataset_name, description="bar", metadata={"demo": True}
        )
        assert dataset.name == dataset_name
        assert dataset.description == "bar"
        assert dataset.metadata == {"demo": True}

        # Update a dataset
        next_name = str(uuid.uuid4())
        dataset.update(name=next_name)
        assert dataset.name == next_name
        assert dataset.description == "bar"

        # Create dataset items
        inputs = [
            {
                "input": {"content": "What is literal?"},
                "expected_output": {"content": "Literal is an observability solution."},
            },
            {
                "input": {"content": "How can I install the sdk?"},
                "expected_output": {"content": "pip install literalai"},
            },
        ]

        [dataset.create_item(**input) for input in inputs]

        for item in dataset.items:
            assert item.dataset_id == dataset.id
            assert item.input is not None
            assert item.expected_output is not None

        # Get a dataset with items
        fetched_dataset = await async_client.api.get_dataset(id=dataset.id)

        assert fetched_dataset is not None

        assert len(fetched_dataset.items) == 2

        # Add step to dataset
        assert step.id is not None
        step_item = fetched_dataset.add_step(step.id)

        assert step_item.input == {"content": "hello world!"}
        assert step_item.expected_output == {"content": "hello back!"}

        # Delete a dataset item
        item_id = fetched_dataset.items[0].id
        fetched_dataset.delete_item(item_id=item_id)

        # Delete a dataset
        fetched_dataset.delete()

        deleted_dataset = await async_client.api.get_dataset(id=dataset.id)

        assert deleted_dataset is None

    @pytest.mark.timeout(5)
    async def test_generation_dataset(self, async_client: AsyncLiteralClient):
        chat_generation = ChatGeneration(
            provider="test",
            model="test",
            messages=[
                {"content": "Hello", "role": "user"},
                {"content": "Hi", "role": "assistant"},
            ],
            message_completion={"content": "Hello back!", "role": "assistant"},
            tags=["test"],
        )
        generation = await async_client.api.create_generation(chat_generation)
        assert generation.id is not None
        dataset_name = str(uuid.uuid4())
        dataset = await async_client.api.create_dataset(
            name=dataset_name, type="generation"
        )
        assert dataset.name == dataset_name

        # Add generation to dataset
        generation_item = dataset.add_generation(generation.id)

        assert generation_item.input == {
            "messages": [
                {"content": "Hello", "role": "user"},
                {"content": "Hi", "role": "assistant"},
            ]
        }
        assert generation_item.expected_output == {
            "content": "Hello back!",
            "role": "assistant",
        }

        # Delete a dataset
        dataset.delete()

    @pytest.mark.timeout(5)
    async def test_dataset_sync(
        self, client: LiteralClient, async_client: AsyncLiteralClient
    ):
        step = await self.create_test_step(async_client)
        dataset_name = str(uuid.uuid4())
        dataset = client.api.create_dataset(
            name=dataset_name, description="bar", metadata={"demo": True}
        )
        assert dataset.name == dataset_name
        assert dataset.description == "bar"
        assert dataset.metadata == {"demo": True}

        # Update a dataset
        next_name = str(uuid.uuid4())
        dataset.update(name=next_name)
        assert dataset.name == next_name
        assert dataset.description == "bar"

        # Create dataset items
        inputs = [
            {
                "input": {"content": "What is literal?"},
                "expected_output": {"content": "Literal is an observability solution."},
            },
            {
                "input": {"content": "How can I install the sdk?"},
                "expected_output": {"content": "pip install literalai"},
            },
        ]
        [dataset.create_item(**input) for input in inputs]

        for item in dataset.items:
            assert item.dataset_id == dataset.id
            assert item.input is not None
            assert item.expected_output is not None

        # Get a dataset with items
        fetched_dataset = client.api.get_dataset(id=dataset.id)

        assert fetched_dataset is not None
        assert len(fetched_dataset.items) == 2

        # Add step to dataset
        assert step.id is not None
        step_item = fetched_dataset.add_step(step.id)

        assert step_item.input == {"content": "hello world!"}
        assert step_item.expected_output == {"content": "hello back!"}

        # Delete a dataset item
        item_id = fetched_dataset.items[0].id
        fetched_dataset.delete_item(item_id=item_id)

        # Delete a dataset
        fetched_dataset.delete()

        assert client.api.get_dataset(id=fetched_dataset.id) is None

    @pytest.mark.timeout(5)
    async def test_prompt(self, async_client: AsyncLiteralClient):
        prompt = await async_client.api.get_prompt(name="Default", version=0)
        project = await async_client.api.get_my_project_id()

        assert prompt is not None
        assert prompt.name == "Default"
        assert prompt.version == 0
        assert prompt.provider == "openai"
        assert prompt.url.endswith(
            f"projects/{project}/playground?name=Default&version=0"
        )

        prompt = await async_client.api.get_prompt(id=prompt.id, version=0)
        assert prompt is not None

        messages = prompt.format_messages()

        expected = """Hello, this is a test value and this

* item 0
* item 1
* item 2

is a templated list."""

        assert messages[0]["content"] == expected

        messages = prompt.format_messages(test_var="Edited value")

        expected = """Hello, this is a Edited value and this

* item 0
* item 1
* item 2

is a templated list."""

        assert messages[0]["content"] == expected

    @pytest.mark.timeout(5)
    async def test_prompt_cache(self, async_client: AsyncLiteralClient):
        prompt = await async_client.api.get_prompt(name="Default", version=0)
        assert prompt is not None

        original_key = async_client.api.api_key
        async_client.api.api_key = "invalid-api-key"

        cached_prompt = await async_client.api.get_prompt(name="Default", version=0)
        assert cached_prompt is not None
        assert cached_prompt.id == prompt.id

        async_client.api.api_key = original_key

    @pytest.mark.timeout(5)
    async def test_prompt_ab_testing(self, client: LiteralClient):
        prompt_name = "Python SDK E2E Tests"

        v0: List[GenerationMessage] = [{"role": "user", "content": "Hello"}]
        v1: List[GenerationMessage] = [{"role": "user", "content": "Hello 2"}]

        prompt_v0 = client.api.get_or_create_prompt(
            name=prompt_name,
            template_messages=v0,
        )

        client.api.update_prompt_ab_testing(
            prompt_v0.name, rollouts=[{"version": 0, "rollout": 100}]
        )

        ab_testing = client.api.get_prompt_ab_testing(name=prompt_v0.name)
        assert len(ab_testing) == 1
        assert ab_testing[0]["version"] == 0
        assert ab_testing[0]["rollout"] == 100

        prompt_v1 = client.api.get_or_create_prompt(
            name=prompt_name,
            template_messages=v1,
        )

        client.api.update_prompt_ab_testing(
            name=prompt_v1.name,
            rollouts=[{"version": 0, "rollout": 60}, {"version": 1, "rollout": 40}],
        )

        ab_testing = client.api.get_prompt_ab_testing(name=prompt_v1.name)
        ab_testing = sorted(ab_testing, key=lambda x: x["version"])

        assert len(ab_testing) == 2
        assert ab_testing[0]["version"] == 0
        assert ab_testing[0]["rollout"] == 60
        assert ab_testing[1]["version"] == 1
        assert ab_testing[1]["rollout"] == 40

    @pytest.mark.timeout(5)
    async def test_gracefulness(self, broken_client: LiteralClient):
        with broken_client.thread(name="Conversation"):
            time.sleep(1)

        broken_client.flush()
        assert True

    @pytest.mark.timeout(5)
    async def test_thread_to_dict(self, client: LiteralClient):
        thread = Thread(id="thread-id", participant_id="participant-id")
        participant = thread.to_dict().get("participant", {})
        assert participant and participant["id"] == "participant-id"

    @pytest.mark.timeout(5)
    async def test_prompt_unique(self, client: LiteralClient):
        prompt = client.api.get_prompt(name="Default", version=0)

        new_prompt = client.api.get_or_create_prompt(
            name=prompt.name,
            template_messages=prompt.template_messages,
            settings=prompt.settings,
            tools=prompt.tools,
        )

        assert new_prompt.id == prompt.id, "Existing prompt should be returned"

    @pytest.mark.timeout(5)
    async def test_experiment_params_optional(self, client: LiteralClient):
        if (ds := client.api.get_dataset(name="test-dataset")) is not None:
            client.api.delete_dataset(id=ds.id)
        dataset = client.api.create_dataset(
            name="test-dataset", description="test-description"
        )
        experiment = dataset.create_experiment(name="test-experiment")
        assert experiment.params is None
        dataset.delete()

    @pytest.mark.timeout(5)
    async def test_experiment_prompt(self, client: LiteralClient):
        prompt_variant_id = client.api.create_prompt_variant(
            name="Default", template_messages=[{"role": "user", "content": "hello"}]
        )
        experiment = client.api.create_experiment(
            name="test-experiment", prompt_variant_id=prompt_variant_id
        )
        assert experiment.params is None
        assert experiment.prompt_variant_id == prompt_variant_id

    @pytest.mark.timeout(5)
    async def test_experiment_run(self, client: LiteralClient):
        experiment = client.api.create_experiment(name="test-experiment-run")

        @client.step(type="run")
        def agent(input):
            return {"content": "hello world!"}

        with client.experiment_item_run():
            input = {"question": "question"}
            output = agent(input)
            item = experiment.log(
                {
                    "scores": [
                        {"name": "context_relevancy", "type": "AI", "value": 0.6}
                    ],
                    "input": input,
                    "output": output,
                }
            )

        assert item.experiment_run_id is not None
        experiment_run = client.api.get_step(item.experiment_run_id)
        assert experiment_run is not None
        assert experiment_run.environment == "experiment"

    @pytest.mark.timeout(5)
    async def test_environment(self, staging_client: LiteralClient):
        run_id: str
        with staging_client.run(name="foo") as run:
            run_id = run.id
        staging_client.event_processor.flush()
        assert run_id is not None
        persisted_run = staging_client.api.get_step(run_id)
        assert persisted_run is not None
        assert persisted_run.environment == "staging"

    @pytest.mark.timeout(5)
    async def test_pii_removal(
        self, client: LiteralClient, async_client: AsyncLiteralClient
    ):
        """Test that PII is properly removed by the preprocess function."""
        import re

        # Define a PII removal function
        def remove_pii(steps):
            # Patterns for common PII
            email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
            phone_pattern = r"\b(\+\d{1,2}\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"
            ssn_pattern = r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"

            for step in steps:
                # Process content field if it exists
                if "output" in step and step["output"]["content"]:
                    # Replace emails with [EMAIL REDACTED]
                    step["output"]["content"] = re.sub(
                        email_pattern, "[EMAIL REDACTED]", step["output"]["content"]
                    )

                    # Replace phone numbers with [PHONE REDACTED]
                    step["output"]["content"] = re.sub(
                        phone_pattern, "[PHONE REDACTED]", step["output"]["content"]
                    )

                    # Replace SSNs with [SSN REDACTED]
                    step["output"]["content"] = re.sub(
                        ssn_pattern, "[SSN REDACTED]", step["output"]["content"]
                    )

            return steps

        # Set the PII removal function on the client
        client.set_preprocess_steps_function(remove_pii)

        @client.thread
        def thread_with_pii():
            thread = client.get_current_thread()

            # User message with PII
            user_step = client.message(
                content="My email is test@example.com and my phone is (123) 456-7890. My SSN is 123-45-6789.",
                type="user_message",
                metadata={"contact_info": "Call me at 987-654-3210"},
            )
            user_step_id = user_step.id

            # Assistant message with PII reference
            assistant_step = client.message(
                content="I'll contact you at test@example.com", type="assistant_message"
            )
            assistant_step_id = assistant_step.id

            return thread.id, user_step_id, assistant_step_id

        # Run the thread
        thread_id, user_step_id, assistant_step_id = thread_with_pii()

        # Wait for processing to occur
        client.flush()

        # Fetch the steps and verify PII was removed
        user_step = client.api.get_step(id=user_step_id)
        assistant_step = client.api.get_step(id=assistant_step_id)

        assert user_step
        assert assistant_step

        user_step_output = user_step.output["content"]  # type: ignore

        # Check user message
        assert "test@example.com" not in user_step_output
        assert "(123) 456-7890" not in user_step_output
        assert "123-45-6789" not in user_step_output
        assert "[EMAIL REDACTED]" in user_step_output
        assert "[PHONE REDACTED]" in user_step_output
        assert "[SSN REDACTED]" in user_step_output

        assistant_step_output = assistant_step.output["content"]  # type: ignore

        # Check assistant message
        assert "test@example.com" not in assistant_step_output
        assert "[EMAIL REDACTED]" in assistant_step_output

        # Clean up
        client.api.delete_step(id=user_step_id)
        client.api.delete_step(id=assistant_step_id)
        client.api.delete_thread(id=thread_id)

        # Reset the preprocess function to avoid affecting other tests
        client.set_preprocess_steps_function(None)
