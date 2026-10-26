"""Load existing task media into native Comfy outputs without generation."""
from __future__ import annotations

if __package__:
    from .crun.results import load_result
else:
    from crun.results import load_result


class CRUNGetImageResult:
    CATEGORY = "CRUN Next/Results"
    FUNCTION = "load"
    RETURN_TYPES = ("IMAGE", "STRING", "FLOAT", "STRING")
    RETURN_NAMES = ("image", "url", "actual_credits", "task_id")
    OUTPUT_NODE = True
    DESCRIPTION = "Load an existing CRUN task into a native IMAGE. Polls only this task ID; never creates, uploads or replaces a generation. Saves the downloaded result under output/CRUNResults."
    KIND = "image"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "task_id": ("STRING", {"forceInput": True, "tooltip": "Connect the task_id output of a CRUN generation, or a STRING with an existing task ID."}),
            "result_index": ("INT", {"default": 0, "min": 0, "max": 99}),
            "timeout_seconds": ("INT", {"default": 1200, "min": 0, "max": 7200, "tooltip": "Zero checks once. A timeout preserves the task ID; run this retrieval again."}),
            "poll_interval": ("FLOAT", {"default": 3.0, "min": 1.0, "max": 30.0, "step": 1.0}),
        }}

    def load(self, task_id, result_index=0, timeout_seconds=1200, poll_interval=3.0):
        if task_id in (None, ""):
            try:
                from comfy_execution.graph_utils import ExecutionBlocker
                blocked = ExecutionBlocker(None)
            except ImportError:
                blocked = None  # Offline inspection without a Comfy executor.
            return {"ui": {"text": ["No task submitted. Upstream is in prepare/estimate or blocked by its optional cap/balance; native preview is waiting for a task ID."]},
                    "result": (blocked, "", -1.0, "")}
        result = load_result(task_id, kind=self.KIND, result_index=result_index,
                             timeout_seconds=timeout_seconds, poll_interval=poll_interval)
        cost = "unavailable" if result[2] < 0 else f"{result[2]:g}"
        return {"ui": {"text": [f"Task {task_id}: {self.KIND} saved locally; actual CRUN credits: {cost}."]}, "result": result}


class CRUNGetVideoResult(CRUNGetImageResult):
    RETURN_TYPES = ("VIDEO", "STRING", "FLOAT", "STRING")
    RETURN_NAMES = ("video", "url", "actual_credits", "task_id")
    DESCRIPTION = "Load an existing CRUN task into Comfy's native VIDEO type for Preview/Save Video. Polls the same task ID; never generates or uploads. Saves the downloaded result under output/CRUNResults."
    KIND = "video"


class CRUNGetAudioResult(CRUNGetImageResult):
    RETURN_TYPES = ("AUDIO", "STRING", "FLOAT", "STRING")
    RETURN_NAMES = ("audio", "url", "actual_credits", "task_id")
    DESCRIPTION = "Recover an existing CRUN speech/music task as native AUDIO for Preview/Save Audio. Reuses verified local media when available; otherwise retrieves this same task ID. Never generates or uploads."
    KIND = "audio"

    @classmethod
    def INPUT_TYPES(cls):
        definition = super().INPUT_TYPES()
        definition["required"]["task_id"] = ("STRING", {"default": "", "tooltip": "Paste an existing task ID or connect one. Completed local media can be reused without contacting CRUN."})
        return definition


NODE_CLASS_MAPPINGS = {
    "CRUN_Next_Get_Image_Result": CRUNGetImageResult,
    "CRUN_Next_Get_Video_Result": CRUNGetVideoResult,
    "CRUN_Next_Get_Audio_Result": CRUNGetAudioResult,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "CRUN_Next_Get_Image_Result": "CRUN • Get Image Result",
    "CRUN_Next_Get_Video_Result": "CRUN • Get Video Result",
    "CRUN_Next_Get_Audio_Result": "CRUN • Get Audio Result",
}
