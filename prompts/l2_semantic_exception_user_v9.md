<verified_base_action>
{{BASE_ACTION_JSON}}
</verified_base_action>

<agent_state>
{{AGENT_STATE_JSON}}
</agent_state>

<event_context>
{{EVENT_CONTEXT_JSON}}
</event_context>

复制已验证的`base_action`，按冻结优先级检查有限例外；政策例外必须有机器可读的`policy_applicability`匹配关系。只输出符合契约的JSON。
