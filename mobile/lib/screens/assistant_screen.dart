import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/assistant_models.dart';
import '../models/api_models.dart';
import '../providers/app_state.dart';
import '../services/assistant_api.dart';
import '../services/api_service.dart';
import '../theme/app_colors.dart';
import '../utils/formatters.dart';
import 'basket_results.dart';

/// A single chat line rendered as a bubble.
class _ChatEntry {
  const _ChatEntry.user(String text)
      : isUser = true,
        text = text,
        turn = null;

  const _ChatEntry.assistant(String text, {this.turn})
      : isUser = false,
        text = text;

  final bool isUser;
  final String text;
  final AssistantTurn? turn;
}

/// M13 AI shopping assistant chat.
///
/// Server contract: the assistant proposes basket changes, the user confirms
/// by tapping Apply. Applying mutates only the local basket and then calls
/// the regular deterministic basket optimizer for verified totals.
class AssistantScreen extends StatefulWidget {
  const AssistantScreen({super.key});

  @override
  State<AssistantScreen> createState() => _AssistantScreenState();
}

class _AssistantScreenState extends State<AssistantScreen> {
  final TextEditingController _input = TextEditingController();
  final ScrollController _scroll = ScrollController();
  AssistantApi? _assistantApi;

  final List<_ChatEntry> _entries = [];
  bool _sending = false;
  bool _initialized = false;
  int _turnSeq = 0;
  _PendingTurn? _pending;
  Set<AssistantProposal> _selected = const {};

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _assistantApi ??= AppScope.of(context).assistantApi ?? HttpAssistantApi();
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _send(String message) async {
    final api = _assistantApi;
    if (api == null || _sending) return;
    final trimmed = message.trim();
    if (trimmed.isEmpty) return;
    setState(() => _entries.add(_ChatEntry.user(trimmed)));
    _input.clear();
    final request = _buildRequest(message: trimmed);
    await _runTurn(api, request);
  }

  AssistantTurnRequest _buildRequest({
    String? message,
    List<AssistantCandidateSelection>? selections,
  }) {
    final state = AppScope.stateOf(context);
    final maxEntries = const AssistantLimits().conversationContextMaxEntries;
    final history = _entries.length > maxEntries
        ? _entries.sublist(_entries.length - maxEntries)
        : _entries;
    return AssistantTurnRequest(
      message: message,
      locale: state.locale.languageCode == 'en' ? 'en' : 'mk',
      conversationContext: history.length <= 1
          ? const []
          : history
              .sublist(0, history.length - 1)
              .map((e) => AssistantConversationEntry(
                    role: e.isUser ? 'user' : 'assistant',
                    content: e.text,
                  ))
              .toList(growable: false),
      currentBasket: state.basketItems
          .take(const AssistantLimits().currentBasketMaxItems)
          .map(AssistantBasketEchoItem.fromBasketItem)
          .toList(growable: false),
      candidateSelections: selections ?? const [],
    );
  }

  Future<void> _runTurn(AssistantApi api, AssistantTurnRequest request) async {
    setState(() => _sending = true);
    final seq = ++_turnSeq;
    final l = AppLocalizations.of(context);
    try {
      final turn = await api.sendTurn(request);
      if (seq != _turnSeq || !mounted) return;
      setState(() {
        _entries.add(_ChatEntry.assistant(
          turn.assistantMessage.isEmpty ? _fallbackMessage(turn, l) : turn.assistantMessage,
          turn: turn,
        ));
        _pending = _PendingTurn(
          turn: turn,
          basketSignature: _basketSignature(AppScope.stateOf(context).basketItems),
        );
        _selected = turn.proposals.toSet();
        _scrollDown();
      });
    } on ApiServiceException catch (_) {
      if (seq != _turnSeq || !mounted) return;
      setState(() {
        _entries.add(_ChatEntry.assistant(l.t('assistant_error_generic')));
        _scrollDown();
      });
    } catch (_) {
      if (seq != _turnSeq || !mounted) return;
      setState(() {
        _entries.add(_ChatEntry.assistant(l.t('assistant_error_generic')));
        _scrollDown();
      });
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _choose(AssistantChoice choice, AssistantChoiceOption option) async {
    final api = _assistantApi;
    if (api == null || _sending || _pending == null) return;
    setState(() {
      _entries.add(_ChatEntry.user('${choice.itemLabel} → ${option.listingName}'));
      _pending = null;
      _selected = const {};
    });
    await _runTurn(
      api,
      _buildRequest(selections: [
        AssistantCandidateSelection(
          itemLabel: choice.itemLabel,
          query: choice.query,
          candidateId: option.candidateId,
          quantity: choice.requestedQuantity ?? 1,
          unit: choice.requestedUnit ?? 'pack',
        ),
      ]),
    );
  }

  Future<void> _applySelected() async {
    final pending = _pending;
    final selected = _selected;
    if (pending == null || selected.isEmpty || _sending) return;
    final state = AppScope.stateOf(context);
    final l = AppLocalizations.of(context);

    // Staleness check: the local basket must not have changed since the turn.
    if (_basketSignature(state.basketItems) != pending.basketSignature) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(l.t('assistant_stale_basket'))),
      );
      return;
    }

    setState(() => _sending = true);
    try {
      var items = List<BasketItem>.from(state.basketItems);
      var mutated = false;
      for (final proposal in selected) {
        if (proposal.isAdd) {
          items = [
            ...items,
            BasketItem(
              localId: AppState.newLocalId(),
              label: proposal.itemLabel,
              canonicalProductId: proposal.canonicalProductId,
              retailerProductId: proposal.retailerProductId,
              quantity: proposal.quantity,
              unit: proposal.unit,
            ),
          ];
          mutated = true;
        } else if (proposal.isReplace) {
          final targetIndex = items
              .indexWhere((item) => _sameIdentity(item, proposal));
          if (targetIndex == -1) {
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text(l.t('assistant_stale_basket'))),
              );
            }
            return;
          }
          items[targetIndex] = items[targetIndex].copyWith(
            quantity: proposal.quantity,
            unit: proposal.unit,
          );
          mutated = true;
        }
      }

      if (!mutated) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(l.t('assistant_nothing_to_apply'))),
        );
        return;
      }
      await state.replaceAllBasketItems(items);

      final optimization = await AppScope.of(context)
          .api
          .optimizeBasket(BasketOptimizeRequest(
            items: items,
            maxStores: 2,
            inStockOnly: true,
          ));

      if (!mounted) return;
      setState(() {
        _entries.add(_ChatEntry.assistant(l.t('assistant_applied')));
        _pending = null;
        _selected = const {};
      });
      if (!mounted) return;
      showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        builder: (sheetContext) => FractionallySizedBox(
          heightFactor: 0.85,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: SingleChildScrollView(
              child: BasketOptimizationResults(result: optimization),
            ),
          ),
        ),
      );
    } on ApiServiceException {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(AppLocalizations.of(context).t('assistant_error_generic'))),
        );
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  void _toggleProposal(AssistantProposal proposal) {
    setState(() {
      final next = Set<AssistantProposal>.from(_selected);
      if (!next.remove(proposal)) {
        next.add(proposal);
      }
      _selected = next;
    });
  }

  void _discardProposals() {
    setState(() {
      _pending = null;
      _selected = const {};
    });
  }

  static bool _sameIdentity(BasketItem item, AssistantProposal proposal) {
    if (proposal.canonicalProductId != null) {
      return item.canonicalProductId == proposal.canonicalProductId;
    }
    if (proposal.retailerProductId != null) {
      return item.retailerProductId == proposal.retailerProductId &&
          item.canonicalProductId == null;
    }
    return false;
  }

  static String _basketSignature(List<BasketItem> items) =>
      items.map((i) => '${i.localId}:${i.quantity}:${i.unit}').join('|');

  void _scrollDown() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 240),
          curve: Curves.easeOut,
        );
      }
    });
  }

  String _fallbackMessage(AssistantTurn turn, AppLocalizations l) {
    final status = turn.status;
    if (status == 'model_unavailable') return l.t('assistant_model_unavailable');
    if (status == 'model_error') return l.t('assistant_model_error');
    return l.t('assistant_error_generic');
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final pending = _pending;

    if (!_initialized) {
      _initialized = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _entries.isEmpty) {
          setState(() {
            _entries.add(_ChatEntry.assistant(l.t('assistant_intro')));
          });
        }
      });
    }

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            if (pending != null && pending.turn.provider.isMock)
              _DemoBanner(isDark: isDark),
            Expanded(
              child: ListView.builder(
                controller: _scroll,
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                itemCount: _entries.length,
                itemBuilder: (context, index) {
                  final entry = _entries[index];
                  final isLast = index == _entries.length - 1;
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: _Bubble(
                      entry: entry,
                      actionable: isLast && entry.turn != null,
                      onChoose: _choose,
                    ),
                  );
                },
              ),
            ),
            if (pending != null && pending.turn.proposals.isNotEmpty)
              _ProposalStrip(
                key: const Key('assistant_apply_strip'),
                pending: pending,
                selected: _selected,
                onToggle: _toggleProposal,
                onDiscard: _discardProposals,
                onApply: _applySelected,
                sending: _sending,
              ),
            _InputBar(controller: _input, sending: _sending, onSend: () => _send(_input.text)),
          ],
        ),
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({
    required this.entry,
    required this.actionable,
    required this.onChoose,
  });

  final _ChatEntry entry;
  final bool actionable;
  final void Function(AssistantChoice, AssistantChoiceOption) onChoose;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final assistantBubbleColor = isDark ? AppColors.darkSurface : AppColors.lightSurface;
    final assistantTextColor = isDark ? AppColors.darkText : AppColors.darkBlue;
    final turn = entry.turn;

    final column = <Widget>[
      Align(
        alignment: entry.isUser ? Alignment.centerRight : Alignment.centerLeft,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 320),
          child: Container(
            margin: const EdgeInsets.symmetric(vertical: 6),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: entry.isUser ? AppColors.primaryOrange : assistantBubbleColor,
              borderRadius: BorderRadius.circular(14),
            ),
            child: Text(
              entry.text,
              style: TextStyle(
                fontSize: 14.5,
                height: 1.35,
                color: entry.isUser ? Colors.white : assistantTextColor,
              ),
            ),
          ),
        ),
      ),
    ];

    if (turn != null && actionable) {
      column.add(_TurnExtras(turn: turn, onChoose: onChoose));
      if (turn.hasChoices) {
        column.add(Padding(
          padding: const EdgeInsets.only(bottom: 4, left: 4),
          child: Text(
            l.t('assistant_pick_option'),
            style: TextStyle(
              fontSize: 12,
              color: isDark ? AppColors.darkSecondary : AppColors.midGray,
            ),
          ),
        ));
      }
    }
    return Column(
      crossAxisAlignment:
          entry.isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
      children: column,
    );
  }
}

/// Non-action turn specifics shown under the latest assistant bubble.
class _TurnExtras extends StatelessWidget {
  const _TurnExtras({required this.turn, required this.onChoose});

  final AssistantTurn turn;
  final void Function(AssistantChoice, AssistantChoiceOption) onChoose;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final muted = isDark ? AppColors.darkSecondary : AppColors.midGray;
    final children = <Widget>[];

    for (final choice in turn.choices) {
      children.add(_ChoiceCard(choice: choice, onPick: (o) => onChoose(choice, o)));
    }
    for (final unresolved in turn.unresolved) {
      children.add(Padding(
        padding: const EdgeInsets.only(left: 4, bottom: 2),
        child: Text(
          '· ${unresolved.label}: ${_reasonLabel(l, unresolved.reason)}',
          style: TextStyle(fontSize: 13, color: muted),
        ),
      ));
    }
    final preview = turn.preview;
    if (preview != null && preview.bestTotalMkd != null) {
      children.add(Padding(
        padding: const EdgeInsets.only(left: 4, top: 2),
        child: Text(
          l.t(
            'assistant_preview_subtotal',
            {
              'total': formatMkd(preview.bestTotalMkd!),
              'store': preview.bestStoreName ?? preview.bestRetailerSlug ?? '—',
            },
          ),
          style: TextStyle(fontSize: 13, color: muted),
        ),
      ));
    }
    if (children.isEmpty) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: children);
  }
}

class _ChoiceCard extends StatelessWidget {
  const _ChoiceCard({required this.choice, required this.onPick});

  final AssistantChoice choice;
  final void Function(AssistantChoiceOption) onPick;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 4),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: isDark ? AppColors.darkSurface : AppColors.lightSurface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isDark ? AppColors.darkBorder : AppColors.lightBorder,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${choice.itemLabel} · ${_choiceReasonLabel(l, choice.reason)}',
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: isDark ? AppColors.darkText : AppColors.darkBlue,
            ),
          ),
          const SizedBox(height: 4),
          ...choice.options.map(
            (option) => _OptionRow(option: option, onPick: () => onPick(option)),
          ),
        ],
      ),
    );
  }
}

class _OptionRow extends StatelessWidget {
  const _OptionRow({required this.option, required this.onPick});

  final AssistantChoiceOption option;
  final VoidCallback onPick;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final muted = isDark ? AppColors.darkSecondary : AppColors.midGray;
    return InkWell(
      onTap: onPick,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(
          children: [
            Icon(
              option.isSubstituteCandidate ? Icons.swap_horiz : Icons.inventory_2_outlined,
              size: 18,
              color: option.isSubstituteCandidate ? AppColors.primaryOrange : muted,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                option.listingName,
                style: TextStyle(
                  fontSize: 13.5,
                  fontWeight: FontWeight.w500,
                  color: isDark ? AppColors.darkText : AppColors.darkBlue,
                ),
              ),
            ),
            Text(
              '${option.retailerSlug}'
              '${option.isSubstituteCandidate ? ' · ${l.t('assistant_substitute_tag')}' : ''}'
              ' · ${option.priceCurrentMkd != null ? formatMkd(option.priceCurrentMkd!) : '—'}',
              style: TextStyle(fontSize: 12, color: muted),
            ),
          ],
        ),
      ),
    );
  }
}

class _DemoBanner extends StatelessWidget {
  const _DemoBanner({required this.isDark});

  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Container(
      width: double.infinity,
      color: isDark ? AppColors.darkSurface : AppColors.lightSurface,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Text(
        l.t('assistant_demo_chip'),
        style: const TextStyle(fontSize: 12, color: AppColors.primaryOrange),
      ),
    );
  }
}

class _InputBar extends StatelessWidget {
  const _InputBar({required this.controller, required this.sending, required this.onSend});

  final TextEditingController controller;
  final bool sending;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 8, 6, 12),
      decoration: BoxDecoration(
        color: isDark ? AppColors.darkSurface : AppColors.lightSurface,
        border: Border(
          top: BorderSide(color: isDark ? AppColors.darkBorder : AppColors.lightBorder),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: controller,
              enabled: !sending,
              maxLength: 500,
              minLines: 1,
              maxLines: 4,
              buildCounter: (context, {required currentLength, required isFocused, maxLength}) => null,
              decoration: InputDecoration(
                hintText: l.t('assistant_input_hint'),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide.none,
                ),
                filled: true,
                fillColor: isDark ? AppColors.darkSurface : AppColors.lightSurface,
                contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              ),
              onSubmitted: (_) => onSend(),
            ),
          ),
          IconButton(
            icon: sending
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.send),
            color: AppColors.primaryOrange,
            onPressed: sending ? null : onSend,
          ),
        ],
      ),
    );
  }
}

/// The latest answered turn plus the local basket signature at reception time.
class _PendingTurn {
  const _PendingTurn({required this.turn, required this.basketSignature});

  final AssistantTurn turn;
  final String basketSignature;
}

/// Apply / dismiss strip with per-proposal checkboxes (default all selected).
class _ProposalStrip extends StatelessWidget {
  const _ProposalStrip({
    super.key,
    required this.pending,
    required this.selected,
    required this.onToggle,
    required this.onDiscard,
    required this.onApply,
    required this.sending,
  });

  final _PendingTurn pending;
  final Set<AssistantProposal> selected;
  final void Function(AssistantProposal) onToggle;
  final VoidCallback onDiscard;
  final VoidCallback onApply;
  final bool sending;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final text = isDark ? AppColors.darkText : AppColors.darkBlue;
    final muted = isDark ? AppColors.darkSecondary : AppColors.midGray;

    return Material(
      color: isDark ? AppColors.darkSurface : AppColors.lightSurface,
      child: Container(
        constraints: const BoxConstraints(maxHeight: 260),
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
        decoration: BoxDecoration(
          border: Border(
            top: BorderSide(color: isDark ? AppColors.darkBorder : AppColors.lightBorder),
          ),
        ),
        child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Flexible(
            child: SingleChildScrollView(
              child: Column(
                children: pending.turn.proposals.map(
                  (proposal) {
                    final detail = proposal.isReplace
                        ? '${proposal.itemLabel} · ${formatQuantity(proposal.oldQuantity ?? 0)} '
                            '${proposal.oldUnit ?? ''} → ${formatQuantity(proposal.quantity)} ${proposal.unit}'
                        : '${proposal.itemLabel} × ${formatQuantity(proposal.quantity)} ${proposal.unit}';
                    return CheckboxListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      controlAffinity: ListTileControlAffinity.leading,
                      value: selected.contains(proposal),
                      onChanged: (_) => onToggle(proposal),
                      title: Text(
                        '${proposal.isAdd ? l.t('assistant_proposal_add') : l.t('assistant_proposal_replace')} · $detail',
                        style: TextStyle(fontSize: 13.5, color: text),
                      ),
                      subtitle: Text(
                        '${proposal.listingName ?? proposal.itemLabel}'
                        '${proposal.priceCurrentMkd != null ? ' · ${formatMkd(proposal.priceCurrentMkd!)}' : ''}'
                        ' · ${proposal.verifiedIdentity ? l.t('assistant_verified') : l.t('assistant_unverified')}',
                        style: TextStyle(fontSize: 12, color: muted),
                      ),
                    );
                  },
                ).toList(growable: false),
              ),
            ),
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              TextButton(
                onPressed: sending ? null : onDiscard,
                child: Text(l.t('assistant_cancel')),
              ),
              const SizedBox(width: 8),
              ElevatedButton(
                key: const Key('assistant_apply'),
                onPressed: sending || selected.isEmpty ? null : onApply,
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.primaryOrange,
                  foregroundColor: Colors.white,
                ),
                child: Text(l.t('assistant_apply')),
              ),
            ],
          ),
        ],
        ),
      ),
    );
  }
}

String _reasonLabel(AppLocalizations l, String reason) {
  switch (reason) {
    case 'no_offers_found':
      return l.t('assistant_reason_no_offers');
    case 'search_failed':
      return l.t('assistant_reason_search_failed');
    case 'tool_budget_exhausted':
      return l.t('assistant_reason_budget');
    case 'candidate_not_confirmed':
      return l.t('assistant_reason_candidate');
    default:
      return l.t('assistant_reason_generic');
  }
}

String _choiceReasonLabel(AppLocalizations l, String reason) {
  switch (reason) {
    case 'multiple_products':
      return l.t('assistant_choice_multiple_products');
    case 'multiple_unverified':
      return l.t('assistant_choice_multiple_unverified');
    case 'no_in_stock_offers':
      return l.t('assistant_choice_no_in_stock_offers');
    default:
      return l.t('assistant_choice_generic');
  }
}
