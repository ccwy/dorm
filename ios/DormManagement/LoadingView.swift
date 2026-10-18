//
//  LoadingView.swift
//  DormManagement
//
//  启动加载遮罩视图，对齐 Android activity_main.xml 的 loadingOverlay：
//  图标 → 旋转指示器 → 标题 → 状态文字 → 进度条 → 百分比
//

import UIKit

class LoadingView: UIView {

    // MARK: - 子视图

    /// 加载图标（用文字"宿"代替图片资源，带脉冲动画）
    private let iconLabel: UILabel = {
        let label = UILabel()
        label.text = "宿"
        label.font = UIFont.boldSystemFont(ofSize: 48)
        label.textColor = UIColor(red: 0.086, green: 0.365, blue: 1.0, alpha: 1.0) // #165DFF
        label.textAlignment = .center
        label.layer.cornerRadius = 20
        label.layer.masksToBounds = true
        label.backgroundColor = UIColor(red: 0.086, green: 0.365, blue: 1.0, alpha: 0.1)
        return label
    }()

    /// 旋转加载指示器（对应 Android loadingSpinner）
    private let spinner: UIActivityIndicatorView = {
        let spinner = UIActivityIndicatorView(style: .gray)
        spinner.color = UIColor(red: 0.086, green: 0.365, blue: 1.0, alpha: 1.0)
        spinner.startAnimating()
        return spinner
    }()

    /// 应用标题（对应 Android loadingTitle）
    let titleLabel: UILabel = {
        let label = UILabel()
        label.text = "行政后勤管理系统"
        label.font = UIFont.boldSystemFont(ofSize: 22)
        label.textColor = UIColor(red: 0.086, green: 0.365, blue: 1.0, alpha: 1.0)
        label.textAlignment = .center
        return label
    }()

    /// 状态文字（对应 Android loadingStatus）
    private let statusLabel: UILabel = {
        let label = UILabel()
        label.text = "正在初始化..."
        label.font = UIFont.systemFont(ofSize: 14)
        label.textColor = UIColor(white: 0.53, alpha: 1.0) // #888888
        label.textAlignment = .center
        label.numberOfLines = 0
        label.lineBreakMode = .byWordWrapping
        return label
    }()

    /// 进度条（对应 Android loadingProgressBar）
    private let progressBar: UIProgressView = {
        let bar = UIProgressView(progressViewStyle: .default)
        bar.progressTintColor = UIColor(red: 0.086, green: 0.365, blue: 1.0, alpha: 1.0)
        bar.trackTintColor = UIColor(white: 0.88, alpha: 1.0) // #E0E0E0
        bar.progress = 0
        return bar
    }()

    /// 进度百分比（对应 Android loadingPercent）
    private let percentLabel: UILabel = {
        let label = UILabel()
        label.text = "0%"
        label.font = UIFont.systemFont(ofSize: 12)
        label.textColor = UIColor(white: 0.67, alpha: 1.0) // #AAAAAA
        label.textAlignment = .center
        return label
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
        for sub in [iconLabel, spinner, titleLabel, statusLabel, progressBar, percentLabel] {
            sub.translatesAutoresizingMaskIntoConstraints = false
            addSubview(sub)
        }
        installConstraints()
    }

    private func installConstraints() {
        NSLayoutConstraint.activate([
            // 图标
            iconLabel.widthAnchor.constraint(equalToConstant: 100),
            iconLabel.heightAnchor.constraint(equalToConstant: 100),
            iconLabel.centerXAnchor.constraint(equalTo: centerXAnchor),
            iconLabel.topAnchor.constraint(equalTo: centerYAnchor, constant: -140),

            // 旋转指示器
            spinner.centerXAnchor.constraint(equalTo: centerXAnchor),
            spinner.topAnchor.constraint(equalTo: iconLabel.bottomAnchor, constant: 12),

            // 标题
            titleLabel.centerXAnchor.constraint(equalTo: centerXAnchor),
            titleLabel.topAnchor.constraint(equalTo: spinner.bottomAnchor, constant: 16),

            // 状态文字
            statusLabel.centerXAnchor.constraint(equalTo: centerXAnchor),
            statusLabel.topAnchor.constraint(equalTo: titleLabel.bottomAnchor, constant: 4),
            statusLabel.widthAnchor.constraint(lessThanOrEqualTo: widthAnchor, multiplier: 0.85),

            // 进度条
            progressBar.centerXAnchor.constraint(equalTo: centerXAnchor),
            progressBar.widthAnchor.constraint(equalToConstant: 240),
            progressBar.topAnchor.constraint(equalTo: statusLabel.bottomAnchor, constant: 20),

            // 百分比
            percentLabel.centerXAnchor.constraint(equalTo: centerXAnchor),
            percentLabel.topAnchor.constraint(equalTo: progressBar.bottomAnchor, constant: 8),
        ])
    }

    // MARK: - 公开方法

    /// 更新进度条和状态文字
    func updateProgress(pct: Int, msg: String) {
        let clamped = max(0, min(100, pct))
        progressBar.setProgress(Float(clamped) / 100.0, animated: true)
        percentLabel.text = "\(clamped)%"
        if !msg.isEmpty {
            statusLabel.text = msg
        }
    }

    /// 显示遮罩
    func show() {
        isHidden = false
        alpha = 1.0
        spinner.startAnimating()
        startPulseAnimation()
    }

    /// 隐藏遮罩（带淡出动画）
    func hide() {
        spinner.stopAnimating()
        stopPulseAnimation()
        UIView.animate(withDuration: 0.3, animations: {
            self.alpha = 0.0
        }, completion: { _ in
            self.isHidden = true
        })
    }

    // MARK: - 图标脉冲动画（对齐 Android loading_pulse.xml 缩放+透明度）

    private var isPulsing = false

    private func startPulseAnimation() {
        guard !isPulsing else { return }
        isPulsing = true
        pulseOnce()
    }

    private func pulseOnce() {
        guard isPulsing else { return }
        UIView.animate(withDuration: 0.8, delay: 0, options: [.curveEaseInOut], animations: {
            self.iconLabel.transform = CGAffineTransform(scaleX: 1.1, y: 1.1)
            self.iconLabel.alpha = 0.7
        }, completion: { _ in
            UIView.animate(withDuration: 0.8, delay: 0, options: [.curveEaseInOut], animations: {
                self.iconLabel.transform = .identity
                self.iconLabel.alpha = 1.0
            }, completion: { _ in
                self.pulseOnce()
            })
        })
    }

    private func stopPulseAnimation() {
        isPulsing = false
        iconLabel.layer.removeAllAnimations()
        iconLabel.transform = .identity
        iconLabel.alpha = 1.0
    }
}