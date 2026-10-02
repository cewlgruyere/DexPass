from typing import Type
reward_reg: dict[str, type] = {}


def register_reward(model):
    reward_reg[model._meta.label] = model
    return model


def get_rewards():
    return reward_reg.values()