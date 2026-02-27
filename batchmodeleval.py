import os
from azure.identity import DefaultAzureCredential 
from azure.ai.projects import AIProjectClient 
from openai.types.eval_create_params import DataSourceConfigCustom
from openai.types.evals.create_eval_jsonl_run_data_source_param import (
    CreateEvalJSONLRunDataSourceParam,
    SourceFileContent,
    SourceFileContentContent,
    SourceFileID,
)

from dotenv import load_dotenv
load_dotenv()

# Azure AI Project endpoint
# Example: https://<account_name>.services.ai.azure.com/api/projects/<project_name>
endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]

# Model deployment name (for AI-assisted evaluators)
# Example: gpt-5-mini
model_deployment_name = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "")

# Dataset details (optional, for reusing existing datasets)
dataset_name = "rfgagentevaldataset"
dataset_version = os.environ.get("DATASET_VERSION", "1")

# Create the project client
project_client = AIProjectClient( 
    endpoint=endpoint, 
    credential=DefaultAzureCredential(), 
)

# Get the OpenAI client for evaluation API
client = project_client.get_openai_client()

def modeleval():
    # Reuse existing dataset if it exists, otherwise upload.
    try:
        dataset = project_client.datasets.get(name=dataset_name, version=dataset_version)
        data_id = dataset.id
        print(f"Using existing dataset: {dataset_name} version {dataset_version}")
    except Exception:
        print(f"Dataset not found, uploading new dataset: {dataset_name} version {dataset_version}")
        data_id = project_client.datasets.upload_file(
            name=dataset_name,
            version=dataset_version,
            file_path="./datarfp.jsonl",
        ).id

    data_source_config = DataSourceConfigCustom(
        type="custom",
        item_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "response": {"type": "string"},
                "ground_truth": {"type": "string"},
            },
            "required": ["query", "response", "ground_truth"],
        },
    )

    testing_criteria = [
        {
            "type": "azure_ai_evaluator",
            "name": "coherence",
            "evaluator_name": "builtin.coherence",
            "initialization_parameters": {
                "deployment_name": model_deployment_name
            },
            "data_mapping": {
                "query": "{{item.query}}",
                "response": "{{item.response}}",
            },
        },
        {
            "type": "azure_ai_evaluator",
            "name": "violence",
            "evaluator_name": "builtin.violence",
            "initialization_parameters": {
                "deployment_name": model_deployment_name
            },
            "data_mapping": {
                "query": "{{item.query}}",
                "response": "{{item.response}}",
            },
        },
        {
            "type": "azure_ai_evaluator",
            "name": "f1",
            "evaluator_name": "builtin.f1_score",
            "data_mapping": {
                "response": "{{item.response}}",
                "ground_truth": "{{item.ground_truth}}",
            },
        },
    ]
    # # Create the evaluation
    # eval_object = client.evals.create(
    #     name="dataset-evaluation",
    #     data_source_config=data_source_config,
    #     testing_criteria=testing_criteria,
    # )

    # # Create a run using the uploaded dataset
    # eval_run = client.evals.runs.create(
    #     eval_id=eval_object.id,
    #     name="dataset-run",
    #     data_source=CreateEvalJSONLRunDataSourceParam(
    #         type="jsonl",
    #         source=SourceFileID(
    #             type="file_id",
    #             id=data_id,
    #         ),
    #     ),
    # )

    input_messages = {
        "type": "template",
        "template": [
            {
                "type": "message",
                "role": "user",
                "content": {
                    "type": "input_text",
                    "text": "{{item.query}}"
                }
            }
        ]
    }

    target = {
        "type": "azure_ai_model",
        "model": "gpt-5-mini",
        "sampling_params": {
            "top_p": 1.0,
            "max_completion_tokens": 2048,
        },
    }

    data_source_config = DataSourceConfigCustom(
        type="custom",
        item_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
        include_sample_schema=True,
    )

    testing_criteria = [
        {
            "type": "azure_ai_evaluator",
            "name": "coherence",
            "evaluator_name": "builtin.coherence",
            "initialization_parameters": {
                "deployment_name": model_deployment_name,
            },
            "data_mapping": {
                "query": "{{item.query}}",
                "response": "{{sample.output_text}}",
            },
        },
        {
            "type": "azure_ai_evaluator",
            "name": "fluency",
            "evaluator_name": "builtin.fluency",
            "initialization_parameters": {"deployment_name": model_deployment_name},
            "data_mapping": {"response": "{{item.response}}"},
        },
        {
            "type": "azure_ai_evaluator",
            "name": "violence",
            "evaluator_name": "builtin.violence",
            "data_mapping": {
                "query": "{{item.query}}",
                "response": "{{sample.output_text}}",
            },
        },
        {
            "type": "azure_ai_evaluator",
            "name": "sexual",
            "evaluator_name": "builtin.sexual",
            "data_mapping": {
                "query": "{{item.query}}",
                "response": "{{sample.output_text}}",
            },
        },
        {
            "type": "azure_ai_evaluator",
            "name": "self_harm",
            "evaluator_name": "builtin.self_harm",
            "data_mapping": {
                "query": "{{item.query}}",
                "response": "{{sample.output_text}}",
            },
        },
        {
            "type": "azure_ai_evaluator",
            "name": "hate_unfairness",
            "evaluator_name": "builtin.hate_unfairness",
            "data_mapping": {
                "query": "{{item.query}}",
                "response": "{{sample.output_text}}",
            },
        },
        {
            "type": "azure_ai_evaluator",
            "name": "protected_material",
            "evaluator_name": "builtin.protected_material",
            "data_mapping": {
                "query": "{{item.query}}",
                "response": "{{sample.output_text}}",
            },
        },
        {
            "type": "azure_ai_evaluator",
            "name": "indirect_attack",
            "evaluator_name": "builtin.indirect_attack",
            "data_mapping": {
                "query": "{{item.query}}",
                "response": "{{sample.output_text}}",
            },
        },
        {
            "type": "azure_ai_evaluator",
            "name": "code_vulnerability",
            "evaluator_name": "builtin.code_vulnerability",
            "data_mapping": {
                "query": "{{item.query}}",
                "response": "{{sample.output_text}}",
            },
        },
        {
            "type": "azure_ai_evaluator",
            "name": "ungrounded_attributes",
            "evaluator_name": "builtin.ungrounded_attributes",
            "data_mapping": {
                "query": "{{item.query}}",
                "context": "{{item.context}}",
                "response": "{{sample.output_text}}",
            },
        },
        {
            "type": "azure_ai_evaluator",
            "name": "groundedness",
            "evaluator_name": "builtin.groundedness",
            "initialization_parameters": {"deployment_name": model_deployment_name},
            "data_mapping": {
                "context": "{{item.context}}",
                "response": "{{item.response}}",
            },
        },
        {
            "type": "azure_ai_evaluator",
            "name": "Groundedness Pro",
            "evaluator_name": "builtin.groundedness_pro",
            "initialization_parameters": {"deployment_name": model_deployment_name},
            "data_mapping": {
                "query": "{{item.query}}",
                "context": "{{item.context}}",
                "response": "{{sample.output_text}}",
            },
        },
        {
            "type": "azure_ai_evaluator",
            "name": "relevance",
            "evaluator_name": "builtin.relevance",
            "initialization_parameters": {"deployment_name": model_deployment_name},
            "data_mapping": {
                "query": "{{item.query}}",
                "context": "{{item.context}}",
                "response": "{{sample.output_text}}",
            },
        },
        {
            "type": "azure_ai_evaluator",
            "name": "retrieval",
            "evaluator_name": "builtin.retrieval",
            "initialization_parameters": {"deployment_name": model_deployment_name},
            "data_mapping": {"query": "{{item.query}}", "context": "{{item.context}}"},
        },
        {
            "type": "azure_ai_evaluator",
            "name": "Similarity",
            "evaluator_name": "builtin.similarity",
            "initialization_parameters": {"deployment_name": model_deployment_name},
            "data_mapping": {
                "query": "{{item.query}}",
                "response": "{{item.response}}",
                "ground_truth": "{{item.ground_truth}}",
            },
        },
        # {
        #     "type": "azure_ai_evaluator",
        #     "name": "BLEUScore",
        #     "evaluator_name": "builtin.bleu_score",
        #     "initialization_parameters": {"deployment_name": model_deployment_name},
        #     "data_mapping": {
        #         "ground_truth": "{{item.ground_truth}}",
        #         "response": "{{item.response}}",
        #     },
        # },
        # {
        #     "type": "azure_ai_evaluator",
        #     "name": "GLEUScore",
        #     "evaluator_name": "builtin.gleu_score",
        #     "initialization_parameters": {"deployment_name": model_deployment_name},
        #     "data_mapping": {
        #         "ground_truth": "{{item.ground_truth}}",
        #         "response": "{{item.response}}",
        #     },
        # },
        # {
        #     "type": "azure_ai_evaluator",
        #     "name": "ROUGEScore",
        #     "evaluator_name": "builtin.rouge_score",
        #     "initialization_parameters": {"deployment_name": model_deployment_name, "rouge_type": "rouge1"},
        #     "data_mapping": {
        #         "ground_truth": "{{item.ground_truth}}",
        #         "response": "{{item.response}}",
        #     },
        # },
        # {
        #     "type": "azure_ai_evaluator",
        #     "name": "METEORScore",
        #     "evaluator_name": "builtin.meteor_score",
        #     "initialization_parameters": {"deployment_name": model_deployment_name, "rouge_type": "rouge1"},
        #     "data_mapping": {
        #         "ground_truth": "{{item.ground_truth}}",
        #         "response": "{{item.response}}",
        #     },
        # },
    ]

    eval_object = client.evals.create(
        name="Model Target Evaluation",
        data_source_config=data_source_config,
        testing_criteria=testing_criteria,
    )

    data_source = {
        "type": "azure_ai_target_completions",
        "source": {
            "type": "file_id",
            "id": data_id,
        },
        "input_messages": input_messages,
        "target": target,
    }

    eval_run = client.evals.runs.create(
        eval_id=eval_object.id,
        name="model-target-evaluation",
        data_source=data_source,
    )

if __name__ == "__main__":
    modeleval()