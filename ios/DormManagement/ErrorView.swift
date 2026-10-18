//
//  ErrorView.swift
//  DormManagement
//
//  错误页面视图，对齐 Android activity_main.xml 的 errorView：
//  错误图标 → 错误信息 → 重试按钮
//

import UIKit

class ErrorView: UIView {

    // MARK: - 回调

    /// 重试按钮回调（由 ViewController 注入）
    var onRetry: (() -> Void)?

    // MARK: - 子视图

    /// 错误图标（用系统符号文字代替图片资源）
    private let iconLabel: UILabel = {
        let label = UILabel()
        label.text = "!"
        label.font = UIFont.boldSystemFont(ofSize: 40)
        label.textColor = .white
        label.textAlignment = .center
        label.backgroundColor = UIColor(red: 0.85, green: 0.2, blue: 0.2, alpha: 1.0)
        label.layer.cornerRadius = 30
        label.layer.masksToBounds = true
        return label
    }()

    /// 错误信息（多行显示）
    let messageLabel: UILabel = {
        let label = UILabel()
        label.text = ""
        label.font = UIFont.systemFont(ofSize: 16)
        label.textColor = UIColor(white: 0.4, alpha: 1.0) // #666666
        label.textAlignment = .center
        label.numberOfLines = 0
        label.lineBreakMode = .byWordWrapping
        return label
    }()

    /// 重试按钮
    private let retryButton: UIButton = {
        let button = UIButton(type: .system)
        button.setTitle("重试", for: .normal)
        button.titleLabel?.font = UIFont.systemFont(ofSize: 14)
        button.setTitleColor(.white, for: .normal)
        button.backgroundColor = UIColor(red: 0.086, green: 0.365, blue: 1.0, alpha: 1.0) // #165DFF
        button.layer.cornerRadius = 6
        button.contentEdgeInsets = UIEdgeInsets(top: 10, left: 32, bottom: 10, right: 32)
        return button
    }()

    // MARK: - 初始化

    override init(frame: CGRect) {
        super.init(frame: frame)
        setupUI()
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        setupUI()
    }

    private func setupUI() {
        backgroundColor = .white
        translatesAutoresizingMaskIntoConstraints = false
        for sub in [iconLabel, messageLabel, retryButton] {
            sub.translatesAutoresizingMaskIntoConstraints = false
            addSubview(sub)
        }
        retryButton.addTarget(self, action: #selector(retryTapped), for: .touchUpInside)
        installConstraints()
    }

    private func installConstraints() {
        NSLayoutConstraint.activate([
            // 图标（垂直居中偏上）
            iconLabel.widthAnchor.constraint(equalToConstant: 60),
            iconLabel.heightAnchor.constraint(equalToConstant: 60),
            iconLabel.centerXAnchor.constraint(equalTo: centerXAnchor),
            iconLabel.topAnchor.constraint(equalTo: centerYAnchor, constant: -90),

            // 错误信息
            messageLabel.centerXAnchor.constraint(equalTo: centerXAnchor),
            messageLabel.leadingAnchor.constraint(greaterThanOrEqualTo: leadingAnchor, constant: 40),
            messageLabel.trailingAnchor.constraint(lessThanOrEqualTo: trailingAnchor, constant: -40),
            messageLabel.topAnchor.constraint(equalTo: iconLabel.bottomAnchor, constant: 24),

            // 重试按钮
            retryButton.centerXAnchor.constraint(equalTo: centerXAnchor),
            retryButton.topAnchor.constraint(equalTo: messageLabel.bottomAnchor, constant: 24),
        ])
    }

    // MARK: - 公开方法

    /// 显示错误页面并设置错误信息
    func show(message: String) {
        messageLabel.text = message
        isHidden = false
    }

    /// 隐藏错误页面
    func hide() {
        isHidden = true
    }

    // MARK: - 事件

    @objc private func retryTapped() {
        onRetry?()
    }
}