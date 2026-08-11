"""Тексты, которые формирует бэкенд: письма и сообщения бота.

Ошибки API здесь не переводятся — они уходят кодом, фразу подбирает фронтенд.
Письмо и сообщение бота переводить больше некому.
"""

from __future__ import annotations

from typing import Any

FALLBACK = "ru"

_MESSAGES: dict[str, dict[str, str]] = {
    "ru": {
        "email.verify.subject": "Подтвердите почту в Re:Pibot",
        "email.verify.body": (
            "Здравствуйте!\n\nЧтобы завершить регистрацию, откройте ссылку:\n{link}\n\n"
            "Ссылка действует сутки. Если вы не регистрировались, письмо можно удалить."
        ),
        "email.password_reset.subject": "Сброс пароля в Re:Pibot",
        "email.password_reset.body": (
            "Чтобы задать новый пароль, откройте ссылку:\n{link}\n\n"
            "Ссылка действует час. Если вы не запрашивали сброс, ничего делать не нужно."
        ),
        "email.change.subject": "Подтвердите новый адрес почты",
        "email.change.body": (
            "Вы указали этот адрес как новый в Re:Pibot. Чтобы подтвердить, откройте ссылку:\n"
            "{link}\n\nСсылка действует час."
        ),
        "payment.succeeded.subject": "Оплата получена",
        "payment.succeeded.body": "Оплата тарифа «{plan}» получена. Подписка продлена.",
        "payment.failed.subject": "Не удалось продлить подписку",
        "payment.failed.body": (
            "Не удалось автоматически продлить тариф «{plan}». Проверьте способ оплаты."
        ),
        "payment.succeeded.bot": "Оплата тарифа «{plan}» получена. Подписка продлена.",
        "payment.failed.bot": (
            "Не удалось автоматически продлить тариф «{plan}». Проверьте способ оплаты."
        ),
        "subscription.expiring_3.subject": "Подписка кончается через три дня",
        "subscription.expiring_3.body": (
            "Тариф «{plan}» действует до {date}. Продлите, чтобы доступ не прервался."
        ),
        "subscription.expiring_3.bot": (
            "Тариф «{plan}» действует до {date}. Продлите, чтобы доступ не прервался."
        ),
        "subscription.expiring_1.subject": "Подписка кончается завтра",
        "subscription.expiring_1.body": (
            "Тариф «{plan}» действует до {date}. Это последний день до перерыва в доступе."
        ),
        "subscription.expiring_1.bot": (
            "Тариф «{plan}» действует до {date}. Это последний день до перерыва в доступе."
        ),
        "subscription.expired.subject": "Подписка закончилась",
        "subscription.expired.body": (
            "Тариф «{plan}» закончился. Доступ отключён — продлите, чтобы вернуть его."
        ),
        "subscription.expired.bot": (
            "Тариф «{plan}» закончился. Доступ отключён — продлите, чтобы вернуть его."
        ),
        "payment.unpaid.subject": "Счёт ждёт оплаты",
        "payment.unpaid.body": "Счёт на тариф «{plan}» ещё не оплачен. Открыть оплату:\n{link}",
        "payment.unpaid.bot": "Счёт на тариф «{plan}» ещё не оплачен. Открыть оплату:\n{link}",
        "ticket.reply.subject": "Поддержка ответила",
        "ticket.reply.body": "Поддержка ответила:\n\n{body}",
        "ticket.reply.bot": "Поддержка ответила:\n\n{body}",
        "winback.step1.subject": "Подписка закончилась вчера",
        "winback.step1.body": (
            "Подписка закончилась вчера. Вернуть доступ можно в один шаг — тариф и оплата на месте."
        ),
        "winback.step1.bot": (
            "Подписка закончилась вчера. Вернуть доступ можно в один шаг — тариф и оплата на месте."
        ),
        "winback.step2.subject": "Личная скидка на возвращение",
        "winback.step2.body": (
            "Держите личную скидку {percent}% на возвращение: код {code}. "
            "Он ваш и действует трое суток."
        ),
        "winback.step2.bot": (
            "Держите личную скидку {percent}% на возвращение: код {code}. "
            "Он ваш и действует трое суток."
        ),
        "winback.step3.subject": "Несколько дней доступа в подарок",
        "winback.step3.body": "Возвращаем {days} дня доступа просто так. Забрать: {link}",
        "winback.step3.bot": "Возвращаем {days} дня доступа просто так. Забрать: {link}",
        "winback.step4.subject": "Последнее письмо о подписке",
        "winback.step4.body": (
            "Это последнее письмо о подписке. Если захотите вернуться — "
            "мы на месте, ничего делать заранее не нужно."
        ),
        "winback.step4.bot": (
            "Это последнее письмо о подписке. Если захотите вернуться — "
            "мы на месте, ничего делать заранее не нужно."
        ),
        # Отписка одна на все маркетинговые виды: человек отказывается от
        # предложений вообще, а не от конкретной ступени лесенки.
        "notify.unsubscribe": "Не присылать предложения",
        "notify.unsubscribed": (
            "Больше не будем присылать предложения. Сообщения об оплате, "
            "окончании подписки и ответах поддержки остаются."
        ),
        "notify.unsubscribe_link": (
            "Не хотите получать такие письма? Отписаться одним нажатием: {link}"
        ),
        "bot.start.greeting": "Здравствуйте, {name}. Это Re:Pibot.",
        "bot.start.open_app": "Открыть приложение",
        "bot.language.choose": "Выберите язык",
        "bot.language.saved": "Язык сохранён",
        "bot.link.done": "Готово: Telegram привязан к вашему аккаунту.",
        "bot.link.already": (
            "К вашему аккаунту уже привязан другой Telegram. Отвяжите его "
            "в кабинете и возьмите новый код."
        ),
        "bot.link.conflict": (
            "У этого Telegram уже есть свой аккаунт со входом по почте или ключу. "
            "Объединить их автоматически нельзя — войдите в тот аккаунт или "
            "напишите в поддержку."
        ),
        "bot.link.expired": "Код недействителен или устарел. Возьмите новый код в кабинете.",
    },
    "en": {
        "email.verify.subject": "Confirm your email for Re:Pibot",
        "email.verify.body": (
            "Hello!\n\nTo finish signing up, open this link:\n{link}\n\n"
            "The link is valid for 24 hours. If you did not sign up, ignore this message."
        ),
        "email.password_reset.subject": "Reset your Re:Pibot password",
        "email.password_reset.body": (
            "To set a new password, open this link:\n{link}\n\n"
            "The link is valid for one hour. If you did not ask for it, no action is needed."
        ),
        "email.change.subject": "Confirm your new email address",
        "email.change.body": (
            "You set this address as your new one in Re:Pibot. To confirm, open this link:\n"
            "{link}\n\nThe link is valid for one hour."
        ),
        "payment.succeeded.subject": "Payment received",
        "payment.succeeded.body": (
            "Payment for the {plan} plan was received. Your subscription was extended."
        ),
        "payment.failed.subject": "Subscription renewal failed",
        "payment.failed.body": (
            "We could not automatically renew the {plan} plan. Check your payment method."
        ),
        "payment.succeeded.bot": (
            "Payment for the {plan} plan was received. Your subscription was extended."
        ),
        "payment.failed.bot": (
            "We could not automatically renew the {plan} plan. Check your payment method."
        ),
        "subscription.expiring_3.subject": "Your subscription ends in three days",
        "subscription.expiring_3.body": (
            "Your {plan} plan is active until {date}. Renew to keep access."
        ),
        "subscription.expiring_3.bot": (
            "Your {plan} plan is active until {date}. Renew to keep access."
        ),
        "subscription.expiring_1.subject": "Your subscription ends tomorrow",
        "subscription.expiring_1.body": (
            "Your {plan} plan is active until {date}. This is the last day before access stops."
        ),
        "subscription.expiring_1.bot": (
            "Your {plan} plan is active until {date}. This is the last day before access stops."
        ),
        "subscription.expired.subject": "Your subscription has ended",
        "subscription.expired.body": (
            "Your {plan} plan has ended. Access is off — renew to bring it back."
        ),
        "subscription.expired.bot": (
            "Your {plan} plan has ended. Access is off — renew to bring it back."
        ),
        "payment.unpaid.subject": "An invoice is waiting",
        "payment.unpaid.body": (
            "The invoice for the {plan} plan is still unpaid. Open payment:\n{link}"
        ),
        "payment.unpaid.bot": (
            "The invoice for the {plan} plan is still unpaid. Open payment:\n{link}"
        ),
        "ticket.reply.subject": "Support replied",
        "ticket.reply.body": "Support replied:\n\n{body}",
        "ticket.reply.bot": "Support replied:\n\n{body}",
        "winback.step1.subject": "Your subscription ended yesterday",
        "winback.step1.body": (
            "Your subscription ended yesterday. Getting access back takes one step — "
            "the plan and the payment are where you left them."
        ),
        "winback.step1.bot": (
            "Your subscription ended yesterday. Getting access back takes one step — "
            "the plan and the payment are where you left them."
        ),
        "winback.step2.subject": "A personal discount to come back",
        "winback.step2.body": (
            "Here is a personal {percent}% discount to come back: code {code}. "
            "It is yours and works for three days."
        ),
        "winback.step2.bot": (
            "Here is a personal {percent}% discount to come back: code {code}. "
            "It is yours and works for three days."
        ),
        "winback.step3.subject": "A few days of access on us",
        "winback.step3.body": "We are giving back {days} days of access. Claim them: {link}",
        "winback.step3.bot": "We are giving back {days} days of access. Claim them: {link}",
        "winback.step4.subject": "The last note about your subscription",
        "winback.step4.body": (
            "This is the last note about your subscription. If you want to come back — "
            "we are here, and nothing needs doing in advance."
        ),
        "winback.step4.bot": (
            "This is the last note about your subscription. If you want to come back — "
            "we are here, and nothing needs doing in advance."
        ),
        "notify.unsubscribe": "Stop sending offers",
        "notify.unsubscribed": (
            "We will not send offers any more. Notices about payments, "
            "subscription expiry and support replies stay."
        ),
        "notify.unsubscribe_link": (
            "Do not want letters like this? Unsubscribe in one click: {link}"
        ),
        "bot.start.greeting": "Hello, {name}. This is Re:Pibot.",
        "bot.start.open_app": "Open the app",
        "bot.language.choose": "Choose a language",
        "bot.language.saved": "Language saved",
        "bot.link.done": "Done: your Telegram is linked to the account.",
        "bot.link.already": (
            "Your account is already linked to a different Telegram. Unlink it "
            "in your account and get a new code."
        ),
        "bot.link.conflict": (
            "This Telegram already has its own account with an email or a key. "
            "We cannot merge them automatically — sign in to that account or "
            "contact support."
        ),
        "bot.link.expired": "The code is invalid or expired. Get a new one in your account.",
    },
}


def has_message(language: str, key: str) -> bool:
    """Есть ли строка под этим ключом.

    Нужна проверке, что у каждого объявленного вида уведомления есть тексты.
    Через `translate` её не сделать: он подставляет параметры, а у разных
    видов они разные, и проверка превратилась бы в перечисление параметров.
    """
    return key in _MESSAGES.get(language, {})


def translate(language: str, key: str, **params: Any) -> str:
    """Берёт строку для языка, при незнакомом языке — русскую."""
    messages = _MESSAGES.get(language, _MESSAGES[FALLBACK])
    template = messages.get(key) or _MESSAGES[FALLBACK][key]
    return template.format(**params) if params else template
