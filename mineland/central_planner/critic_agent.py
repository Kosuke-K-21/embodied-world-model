"""
Critic Agent
"""

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_openai import ChatOpenAI

from .prompt_template import load_prompt


class CriticInfo(BaseModel):
    reasoning: str = Field(description="reasoning")
    success: bool = Field(description="success")
    critique: str = Field(description="critique")


class CriticAgent:
    """
    Critic Agent
    Generate a critique for the last short-term plan.
    There are two modes: "auto" for LLM/VLM critique generation and "manual" for manual critique generation.
    Return the critique to the brain.
    """

    def __init__(
        self,
        FAILED_TIMES_LIMIT=2,
        model_name="gpt-4-vision-preview",
        base_url=None,
        max_tokens=256,
        temperature=0,
        save_path="./save",
        vision=True,
    ):
        self.plan_failed_count = 0
        self.vision = vision
        model = ChatOpenAI(
            model=model_name,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        parser = JsonOutputParser(pydantic_object=CriticInfo)
        self.chain = model | parser

        self.save_path = save_path

    def render_system_message(self):
        prompt = load_prompt("critic")
        return SystemMessage(content=prompt)

    def render_human_message(self, short_term_plan, obs):
        observation = []
        short_term_plan = short_term_plan["short_term_plan"]
        observation.append({"type": "text", "text": short_term_plan})
        observation.append({"type": "text", "text": str(obs).replace(" ", "")})
        try:
            image_base64 = obs["rgb_base64"]
            if image_base64 != "":
                observation.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}",
                            "detail": "auto",
                        },
                    }
                )
        except:
            print("No image in observation")
            pass

        human_message = HumanMessage(content=observation)
        return human_message

    def check_task_success(self, messages, max_retries=5, verbose=False):
        if max_retries == 0:
            print("\033[31mFailed to parse Critic Agent response. Consider updating your prompt.\033[0m")
            return False, ""

        if messages[1] is None:
            return False, ""

        try:
            critic_info = self.chain.invoke(messages)
            # print(critic_info)
            if verbose:
                print(f"\033[31m****Critic Agent****\n{critic_info}\033[0m")
                with open(f"{self.save_path}/log.txt", "a+") as f:
                    f.write(f"****Critic Agent****\n{critic_info}\n")
            assert critic_info["success"] in [True, False]
            assert critic_info["critique"] != ""
            return critic_info["success"], critic_info["critique"]
        except Exception as e:
            print(f"\033[31mError parsing critic response: {e} Trying again!\033[0m")
            return self.check_task_success(
                messages=messages,
                max_retries=max_retries - 1,
            )

    def critic(self, short_term_plan, obs, max_retries=5, verbose=False):
        """
        params:
            short_term_plan: short term plan
            obs: observation
            max_retries: max retries
        return:
            next_step: next step
            success: success
            critique: critique
        """
        human_message = self.render_human_message(short_term_plan, obs)

        messages = [self.render_system_message(), human_message]

        success, critique = self.check_task_success(messages=messages, max_retries=max_retries, verbose=verbose)

        if success:
            next_step = "brain"
            self.plan_failed_count = 0
        else:
            next_step = "action"
            self.plan_failed_count += 1
            if self.plan_failed_count >= self.FAILED_TIMES_LIMIT:
                next_step = "brain"
                critique = "failed"
                self.plan_failed_count = 0

        return next_step, success, critique