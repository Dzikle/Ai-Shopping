/// Shared basket add sheet used by offer cards and comparison screens.
library;

import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/api_models.dart';
import '../providers/app_state.dart';

const _basketUnits = ['g', 'kg', 'ml', 'l', 'pcs', 'pack'];

/// Shows a modal sheet to pick quantity/unit and adds the item to the basket.
Future<void> showAddToBasketSheet(
  BuildContext context, {
  required String label,
  int? canonicalProductId,
  String sourceUnit = 'pack',
}) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (sheetContext) => _AddToBasketSheet(
      label: label,
      canonicalProductId: canonicalProductId,
      initialUnit: sourceUnit,
    ),
  );
}

class _AddToBasketSheet extends StatefulWidget {
  const _AddToBasketSheet({
    required this.label,
    required this.canonicalProductId,
    required this.initialUnit,
  });

  final String label;
  final int? canonicalProductId;
  final String initialUnit;

  @override
  State<_AddToBasketSheet> createState() => _AddToBasketSheetState();
}

class _AddToBasketSheetState extends State<_AddToBasketSheet> {
  late final TextEditingController _controller =
      TextEditingController(text: '1');
  late String _unit =
      _basketUnits.contains(widget.initialUnit) ? widget.initialUnit : 'pack';
  String? _error;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final l = AppLocalizations.of(context);
    final value = double.tryParse(_controller.text.replaceFirst(',', '.'));
    if (value == null || value <= 0) {
      setState(() => _error = l.t('add_to_basket_invalid_quantity'));
      return;
    }
    final state = AppScope.stateOf(context);
    await state.addBasketItem(BasketItem(
      localId: AppState.newLocalId(),
      label: widget.label,
      canonicalProductId: widget.canonicalProductId,
      quantity: value,
      unit: _unit,
    ));
    if (!mounted) return;
    Navigator.of(context).pop();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(l.t('add_to_basket_added'))),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Padding(
      padding: EdgeInsets.only(
        left: 16,
        right: 16,
        top: 16,
        bottom: MediaQuery.of(context).viewInsets.bottom + 16,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            l.t('add_to_basket_title'),
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 4),
          Text(
            widget.label,
            style: TextStyle(
              fontSize: 13,
              color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.7),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _controller,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration: InputDecoration(
                    labelText: l.t('add_to_basket_quantity'),
                    errorText: _error,
                  ),
                  onSubmitted: (_) => _submit(),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: DropdownButtonFormField<String>(
                  initialValue: _unit,
                  decoration: InputDecoration(
                    labelText: l.t('add_to_basket_unit'),
                  ),
                  items: _basketUnits
                      .map((u) => DropdownMenuItem(
                            value: u,
                            child: Text(l.unit(u)),
                          ))
                      .toList(growable: false),
                  onChanged: (value) => setState(() => _unit = value ?? 'pack'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: _submit,
              child: Text(l.t('common_add')),
            ),
          ),
        ],
      ),
    );
  }
}
